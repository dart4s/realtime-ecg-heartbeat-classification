"""
Kafka Producer — Simulates multi-hospital ECG telemetry sources by streaming
heartbeat records (with Faker-generated patient demographics) to Kafka.

Usage (run from source_code/ directory):
    python stream/producer.py
"""

import json
import logging
import os
import socket
import sys
import time

import pandas as pd
from faker import Faker
from kafka import KafkaProducer
from datetime import datetime

# ---------------------------------------------------------------------------
# Setup — ensure config is importable from the stream/ package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    KAFKA_API_VERSION,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_SECURITY_PROTOCOL,
    KAFKA_TOPIC,
    SEND_INTERVAL_SECONDS,
    SSL_CA_FILE,
    SSL_CERT_FILE,
    SSL_KEY_FILE,
    STREAM_DATA_PATH,
    USE_LOCAL_KAFKA,
)

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
# Faker — Generate patient demographic metadata
# ---------------------------------------------------------------------------
fake = Faker()


def generate_patient_metadata() -> dict:
    """
    Generate synthetic patient demographic metadata using Faker.

    Returns a dict with keys: Patient ID, Patient Name, Age, Gender,
    Hospital Name, Hospital Address.
    """
    return {
        "Patient ID": fake.uuid4()[:8].upper(),
        "Patient Name": fake.name(),
        "Age": fake.random_int(min=18, max=95),
        "Gender": fake.random_element(elements=("Male", "Female")),
        "Hospital Name": fake.company() + " Hospital",
        "Hospital Address": fake.address().replace("\n", ", "),
    }

# ---------------------------------------------------------------------------
# Kafka Producer
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


def create_producer() -> KafkaProducer:
    """Create and return a Kafka producer (supports PLAINTEXT or SSL)."""
    if not is_kafka_available(KAFKA_BOOTSTRAP_SERVERS):
        raise ConnectionRefusedError(f"Kafka broker at {KAFKA_BOOTSTRAP_SERVERS} is not reachable")

    try:
        producer_kwargs = {
            "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
            "security_protocol": KAFKA_SECURITY_PROTOCOL,
            "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
            "key_serializer": lambda v: json.dumps(v).encode("ascii"),
            "api_version": KAFKA_API_VERSION,
            "request_timeout_ms": 3000,
        }

        # Nếu là Aiven SSL thì mới truyền cert files
        if not USE_LOCAL_KAFKA and SSL_CA_FILE:
            producer_kwargs.update({
                "ssl_cafile": SSL_CA_FILE,
                "ssl_certfile": SSL_CERT_FILE,
                "ssl_keyfile": SSL_KEY_FILE,
            })

        producer = KafkaProducer(**producer_kwargs)
        logger.info(
            "Kafka producer connected to %s (Protocol: %s)",
            KAFKA_BOOTSTRAP_SERVERS,
            KAFKA_SECURITY_PROTOCOL,
        )
        return producer
    except Exception as exc:
        logger.error("Failed to connect to Kafka: %s", exc)
        raise

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # Load ECG stream dataset
    if not os.path.exists(STREAM_DATA_PATH):
        logger.error("Dataset not found at %s. Please generate or provide the CSV file.", STREAM_DATA_PATH)
        return

    data = pd.read_csv(STREAM_DATA_PATH)
    total = data.shape[0]
    logger.info("Loaded %d ECG records from %s", total, STREAM_DATA_PATH)

    # Attempt to connect to Kafka; fall back to Direct Stream if Kafka is not available
    producer = None
    model = None
    try:
        producer = create_producer()
    except Exception as exc:
        logger.warning(
            "Kafka broker is not reachable at %s (%s).", KAFKA_BOOTSTRAP_SERVERS, exc
        )
        logger.info("➡️  Switching to Direct Stream Simulation Mode (Runs without Kafka).")
        from consumer import load_model, predict, append_to_csv
        from config import RECEIVED_DATA_PATH
        model = load_model()

    for i in range(total):
        cur_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # ECG signal (187 sample points)
        ecg_data = data.iloc[i, :187].values.tolist()

        # Any extra columns already in the CSV
        info_data = data.iloc[i, 188:].to_dict()

        # Build the message payload
        value = {
            "Time": cur_time,
            "ECG Heartbeat": ecg_data,
        }

        # Merge Faker-generated patient demographics
        value.update(generate_patient_metadata())

        # Merge any existing columns from the stream CSV
        value.update(info_data)

        if producer is not None:
            # Mode A: Send via Kafka
            key = {"key": "ecg_heartbeat"}
            try:
                future = producer.send(topic=KAFKA_TOPIC, key=key, value=value)
                future.get(timeout=10)
                logger.info(
                    "[Kafka] Message %d/%d sent at %s — Patient: %s",
                    i + 1,
                    total,
                    cur_time,
                    value.get("Patient Name", "N/A"),
                )
            except Exception as exc:
                logger.error("Failed to send message %d: %s", i + 1, exc)
        else:
            # Mode B: Direct Stream Simulation (Inference + Append to CSV & DB)
            from consumer import predict, append_to_csv
            from config import RECEIVED_DATA_PATH
            label = predict(model, ecg_data)
            value["Result"] = label
            append_to_csv(RECEIVED_DATA_PATH, value)
            try:
                from database import insert_telemetry_record, insert_system_log
                insert_telemetry_record(value)
                insert_system_log("PRODUCER", "INFO", f"Streamed record #{i+1} for patient {value.get('Patient Name', 'Unknown')}")
            except Exception as db_err:
                logger.warning("Database write warning: %s", db_err)
            logger.info(
                "[Direct Stream] Record %d/%d sent at %s — Patient: %s | Classified: [%s]",
                i + 1,
                total,
                cur_time,
                value.get("Patient Name", "N/A"),
                label,
            )

        time.sleep(SEND_INTERVAL_SECONDS)

    if producer is not None:
        producer.close()
    logger.info("Stream completed. All %d records processed.", total)


if __name__ == "__main__":
    main()
