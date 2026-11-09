"""
Shared configuration for the Real-time ECG Heartbeat Classification Pipeline.

All Kafka, file path, model, and label configurations are centralized here.
Supports overriding via environment variables for deployment flexibility.
"""

import os

# ============================================================================
# Kafka Configuration (Supports Local PLAINTEXT and Aiven SSL)
# ============================================================================
# Đặt biến môi trường USE_LOCAL_KAFKA=true nếu muốn chạy thử Kafka Local không cần SSL
USE_LOCAL_KAFKA = os.environ.get("USE_LOCAL_KAFKA", "true").lower() in ("true", "1", "yes")

KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "ECG_TOPIC")
KAFKA_GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "ds104")
KAFKA_API_VERSION = (2, 12, 0)

if USE_LOCAL_KAFKA:
    # Kafka cục bộ (Docker hoặc cài trực tiếp trên máy)
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    SSL_KEY_FOLDER = None
    SSL_CA_FILE = None
    SSL_CERT_FILE = None
    SSL_KEY_FILE = None
else:
    # Kafka Aiven Cloud (Cần các file SSL certs)
    KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS",
        "kafka-7706a89-ds104.a.aivencloud.com:25429",
    )
    KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "SSL")
    SSL_KEY_FOLDER = os.environ.get("SSL_KEY_FOLDER", "stream/key/")
    SSL_CA_FILE = os.path.join(SSL_KEY_FOLDER, "ca.pem")
    SSL_CERT_FILE = os.path.join(SSL_KEY_FOLDER, "service.cert")
    SSL_KEY_FILE = os.path.join(SSL_KEY_FOLDER, "service.key")

# ============================================================================
# File Paths (relative to source_code/)
# ============================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))

RECEIVED_DATA_PATH = os.path.join(DATA_DIR, "received_data.csv")
STREAM_DATA_PATH = os.path.join(DATA_DIR, "mitbih_stream.csv")
TRAIN_DATA_PATH = os.path.join(DATA_DIR, "mitbih_train.csv")
TEST_DATA_PATH = os.path.join(DATA_DIR, "mitbih_test.csv")
HOSPITAL_DATA_PATH = os.path.join(DATA_DIR, "hospital.csv")
DB_PATH = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "ecg_pipeline.db"))

MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(BASE_DIR, "model", "ecg_conv_model.keras"))
BANNER_IMAGE_PATH = os.path.join(BASE_DIR, "material", "hb2.png")

# ============================================================================
# AAMI EC57 Standard — Label Mapping
# ============================================================================
LABEL_MAP = {
    0: "N",
    1: "S",
    2: "V",
    3: "F",
    4: "Q",
}

LABEL_DESCRIPTIONS = {
    "N": "Normal / Bundle branch block / Escapes",
    "S": "Atrial premature / Supraventricular premature",
    "V": "Premature ventricular contraction / Ventricular escape",
    "F": "Fusion of ventricular and normal",
    "Q": "Paced / Unclassifiable",
}

# Number of AAMI classes
NUM_CLASSES = 5

# ECG signal length (187 sample points per heartbeat)
ECG_SIGNAL_LENGTH = 187

# ============================================================================
# Alert Configuration
# ============================================================================
# Classes that trigger health alerts (anything other than Normal)
ALERT_CLASSES = {"S", "V", "F", "Q"}

ALERT_SEVERITY = {
    "S": {
        "level": "⚠️ Warning",
        "color": "orange",
        "description": "Atrial premature / Supraventricular premature beat detected",
    },
    "V": {
        "level": "🔴 Critical",
        "color": "red",
        "description": "Premature ventricular contraction / Ventricular escape detected",
    },
    "F": {
        "level": "🟡 Caution",
        "color": "yellow",
        "description": "Fusion of ventricular and normal beat detected",
    },
    "Q": {
        "level": "ℹ️ Info",
        "color": "blue",
        "description": "Paced / Unclassifiable beat detected",
    },
}

# ============================================================================
# Streaming Configuration
# ============================================================================
# Delay between sending consecutive messages (seconds)
SEND_INTERVAL_SECONDS = float(os.environ.get("SEND_INTERVAL_SECONDS", "3"))

# Maximum number of recent alerts shown in the dashboard
MAX_DASHBOARD_ALERTS = 10

# Dashboard refresh interval (seconds)
DASHBOARD_REFRESH_SECONDS = float(os.environ.get("DASHBOARD_REFRESH_SECONDS", "3"))
