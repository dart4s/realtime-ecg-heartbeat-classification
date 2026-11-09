"""
Kafka Consumer — Receives ECG heartbeat data from Kafka, runs real-time
classification using the trained 1D-CNN model, and appends results to CSV.

Usage (run from source_code/ directory):
    python stream/consumer.py
"""

import csv
import json
import logging
import os
import socket
import sys

import numpy as np
import pandas as pd
import tensorflow as tf
from kafka import KafkaConsumer

# ---------------------------------------------------------------------------
# Setup — ensure config is importable from the stream/ package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_GROUP_ID,
    KAFKA_SECURITY_PROTOCOL,
    KAFKA_TOPIC,
    LABEL_MAP,
    MODEL_PATH,
    RECEIVED_DATA_PATH,
    SSL_CA_FILE,
    SSL_CERT_FILE,
    SSL_KEY_FILE,
    USE_LOCAL_KAFKA,
)

import warnings
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kafka Consumer
# ---------------------------------------------------------------------------
def is_kafka_available(host_port: str) -> bool:
    """Quickly probe if Kafka broker host:port is listening."""
    try:
        parts = host_port.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 9092
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def create_consumer() -> KafkaConsumer:
    """Create and return a Kafka consumer (supports PLAINTEXT or SSL)."""
    if not is_kafka_available(KAFKA_BOOTSTRAP_SERVERS):
        raise ConnectionRefusedError(f"Kafka broker at {KAFKA_BOOTSTRAP_SERVERS} is not reachable")

    try:
        consumer_kwargs = {
            "auto_offset_reset": "earliest",
            "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
            "group_id": KAFKA_GROUP_ID,
            "security_protocol": KAFKA_SECURITY_PROTOCOL,
            "request_timeout_ms": 3000,
        }

        # Nếu là Aiven SSL thì mới truyền cert files
        if not USE_LOCAL_KAFKA and SSL_CA_FILE:
            consumer_kwargs.update({
                "ssl_cafile": SSL_CA_FILE,
                "ssl_certfile": SSL_CERT_FILE,
                "ssl_keyfile": SSL_KEY_FILE,
            })

        consumer = KafkaConsumer(KAFKA_TOPIC, **consumer_kwargs)
        logger.info(
            "Kafka consumer connected to %s (Protocol: %s)",
            KAFKA_BOOTSTRAP_SERVERS,
            KAFKA_SECURITY_PROTOCOL,
        )
        return consumer
    except Exception as exc:
        logger.error("Failed to connect to Kafka: %s", exc)
        raise

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def load_model(path: str = MODEL_PATH):
    """Load the trained 1D-CNN Keras model."""
    try:
        model = tf.keras.models.load_model(path)
        logger.info("Model loaded from %s", path)
        return model
    except Exception as exc:
        logger.error("Failed to load model from %s: %s", path, exc)
        raise


def predict(model, data: list) -> str:
    """
    Run a single ECG heartbeat through the model and return the
    AAMI class label (N / S / V / F / Q).
    """
    x = np.array([float(i) for i in data]).reshape(1, -1)
    y_pred = model.predict(x, verbose=0)
    y_class = int(np.argmax(y_pred, axis=-1)[0])
    return LABEL_MAP.get(y_class, "N")

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def is_csv_empty(file_path: str) -> bool:
    """Return True if *file_path* does not exist or contains no data rows."""
    if not os.path.exists(file_path):
        return True
    try:
        with open(file_path, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    return False
    except Exception:
        return True
    return True


def append_to_csv(file_path: str, record: dict) -> None:
    """Append a single record dict to *file_path*, writing header if needed."""
    write_header = is_csv_empty(file_path)
    with open(file_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(list(record.keys()))
        writer.writerow(list(record.values()))

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    try:
        consumer = create_consumer()
    except Exception as exc:
        logger.warning("Kafka broker is not reachable: %s", exc)
        logger.info("ℹ️  Tip: If running without Kafka, you can start 'python stream/producer.py' directly — it will auto-switch to Direct Stream Simulation mode and stream real-time data to 'python app.py'!")
        logger.info("ℹ️  To run with local Kafka, start a broker with: docker run -d -p 9092:9092 bashj79/kafka-kraft:latest")
        return

    model = load_model()

    logger.info("Waiting for messages on topic '%s' …", KAFKA_TOPIC)

    for i, msg in enumerate(consumer):
        try:
            # Decode the Kafka message
            value = json.loads(msg.value.decode("utf-8"))
            ecg_data = value["ECG Heartbeat"]
            get_time = value["Time"]

            logger.info(
                "Received message #%d from producer at %s", i + 1, get_time,
            )

            # Run real-time classification
            label = predict(model, ecg_data)
            value["Result"] = label

            # Persist to CSV and SQLite Database
            append_to_csv(RECEIVED_DATA_PATH, value)
            try:
                from database import insert_telemetry_record, insert_system_log
                insert_telemetry_record(value)
                insert_system_log("CONSUMER", "INFO", f"Classified [{label}] for patient {value.get('Patient Name', 'Unknown')}")
            except Exception as db_err:
                logger.warning("Database write warning: %s", db_err)

            logger.info(
                "Classified as [%s] — record saved (%s)", label, RECEIVED_DATA_PATH,
            )
        except KeyError as exc:
            logger.warning("Malformed message (missing key %s), skipping.", exc)
        except Exception as exc:
            logger.error("Error processing message #%d: %s", i + 1, exc)


if __name__ == "__main__":
    main()
