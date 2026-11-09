# Real-time ECG Heartbeat Classification Pipeline

An end-to-end distributed data engineering and deep learning system designed to ingest, process, and classify real-time electrocardiogram (ECG) heartbeat signals for early arrhythmia detection.

---

## 🏗️ System Architecture & Workflow

```mermaid
flowchart TD
    subgraph Ingestion["1. Data Ingestion & Patient Demographics"]
        D1["MIT-BIH Arrhythmia Dataset (109,446 records)"]
        D2["Faker Demographics (Name, Age, Gender, ID)"]
        D3["Multi-Hospital Directory (hospital.csv)"]
        PROD["Telemetry Producer (stream/producer.py)"]
        D1 --> PROD
        D2 --> PROD
        D3 --> PROD
    end

    subgraph Broker["2. Message Broker & Streaming Engine"]
        K_LOCAL["Local Apache Kafka (Docker KRaft :9092)"]
        K_CLOUD["Aiven Cloud Kafka (SSL Mutual TLS)"]
        K_DIRECT["Direct Stream Engine (Zero-Broker Fallback)"]
        PROD -->|"Topic: ECG_TOPIC"| K_LOCAL
        PROD -.->|"SSL Certs"| K_CLOUD
        PROD -.->|"Offline Fallback"| K_DIRECT
    end

    subgraph Inference["3. Stream Processing & Deep Learning Inference"]
        CONS["Stream Consumer (stream/consumer.py)"]
        MODEL["1D-CNN Model (ecg_conv_model.keras - 98.2% Acc)"]
        ALERT["Arrhythmia Classifier & Severity Engine (N, S, V, F, Q)"]
        K_LOCAL --> CONS
        K_CLOUD --> CONS
        CONS --> MODEL
        MODEL --> ALERT
        K_DIRECT --> ALERT
    end

    subgraph Storage["4. Persistent Data Layer (SQLite WAL)"]
        DB[("SQLite Database: data/ecg_pipeline.db")]
        T_REC["telemetry_records (Signals, Predictions, Demographics)"]
        T_LOG["system_logs (Audit Trail, Alerts, Service Events)"]
        F_CSV["CSV Telemetry Backup: data/received_data.csv"]
        ALERT -->|"ACID Transaction"| DB
        ALERT --> F_CSV
        DB --> T_REC
        DB --> T_LOG
    end

    subgraph Presentation["5. Web Application & Analytics Dashboard"]
        FLASK["Flask Application Server (app.py - Port 5000/8080)"]
        WEB["Responsive Web Dashboard (HTML5 / CSS3 / Chart.js)"]
        SQL_UI["SQLite Live Query Console (In-Browser SQL Editor)"]
        SOUND["Audio Arrhythmia Alarm (Web Audio API Synthesizer)"]
        TEST_BTN["1-Click Heartbeat Simulator (⚡ Test Button)"]
        
        DB --> FLASK
        FLASK --> WEB
        FLASK --> SQL_UI
        WEB --> SOUND
        TEST_BTN --> FLASK
    end
```

The platform simulates a multi-source global telemetry setup and processes streaming medical data through a robust pipeline:

1. **Global Data Ingestion & Streaming (`Apache Kafka` & `Aiven Cloud`):**
   - Simulated multi-hospital data sources transmitting continuous ECG records through an **Apache Kafka** cluster hosted on **Aiven Cloud** (Hong Kong server) acting as a centralized broker.
   - Leveraged Python's `Faker` library to synchronously generate patient demographic metadata alongside telemetry streams.
2. **Distributed Preprocessing & Transformation (`Spark SQL` & `PySpark`):**
   - Processed the benchmark **MIT-BIH Arrhythmia Dataset** (`109,446 samples` across 5 AAMI standard classes).
   - Applied **Spark SQL** for sliding windowing (10s intervals), signal amplitude normalization ($[0, 1]$), R-peak extraction, 188-length zero-padding, and **Over-Resampling** to resolve severe class imbalance (e.g., normal class $N$ at 82.8% vs. fusion class $F$ at 0.7%).
3. **Distributed Model Training (`TensorFlow` & Deep Learning):**
   - Trained and evaluated 5 neural network architectures (**1D-CNN, GRU, LSTM, RNN, MLP**) across distributed hardware (`2x GPUs` and `8x TPUs`).
   - Selected the top-performing **1D-CNN model** to execute real-time classification.
4. **Interactive Monitoring Dashboard (`Flask`, `HTML5/CSS3`, `Chart.js` & `Streamlit`):**
   - Deployed a responsive web dashboard featuring live ECG waveform visualization, real-time health alerts, Dark/Light theme switching, audio arrhythmia chime, and an embedded **SQLite Live Query Console** for in-browser data analytics.

### 🔄 End-to-End Real-Time Data Flow

```mermaid
sequenceDiagram
    autonumber
    actor Doctor as Doctor / Monitor
    participant UI as Web Dashboard (Browser)
    participant Flask as Flask Server (app.py)
    participant Consumer as Consumer & 1D-CNN (consumer.py)
    participant Broker as Kafka Broker (:9092)
    participant Producer as Telemetry Producer (producer.py)
    participant DB as SQLite (ecg_pipeline.db)

    Note over Producer,Broker: 1. Telemetry Ingestion Phase
    Producer->>Producer: Sample 187 ECG points + Gen Faker Demographics
    alt Kafka Broker Online
        Producer->>Broker: Publish JSON (Patient Info + 187 Signals)
        Broker->>Consumer: Poll message stream
        Consumer->>Consumer: 1D-CNN Model Inference (Predict N, S, V, F, Q)
        Consumer->>DB: INSERT into telemetry_records (WAL Mode)
    else Direct Mode Fallback
        Producer->>Consumer: Direct In-Memory Inference
        Consumer->>DB: INSERT into telemetry_records
    end

    Note over UI,Flask: 2. Real-Time Monitoring Phase
    UI->>Flask: GET /api/telemetry (Polled every 3s)
    Flask->>DB: Query latest 50 records & aggregate KPIs
    DB-->>Flask: Return records, alerts, and trend distribution
    Flask-->>UI: JSON Payload (Waveform points, KPIs, Alerts)
    UI->>UI: Update Chart.js Waveform & Doughnut Distribution
    opt Critical Arrhythmia (V or F)
        UI->>Doctor: Play Two-Tone Audio Alarm & Flash Alert Tag
    end

    Note over UI,DB: 3. Interactive SQL Analysis Phase
    Doctor->>UI: Write Custom SQL Query (or Select Template)
    UI->>Flask: POST /api/query { query }
    Flask->>Flask: Read-Only Security Inspection
    Flask->>DB: Execute SELECT Query
    DB-->>Flask: Query Result (Columns + Rows)
    Flask-->>UI: JSON (Data + Execution Duration)
    UI-->>Doctor: Render Dynamic Results Grid & Enable CSV Download
```

---

## 📸 Dashboard Screenshots

| Light Mode Dashboard | Dark Mode Dashboard |
| :---: | :---: |
| ![Light Mode Dashboard](docs/screenshots/dashboard_light.png) | ![Dark Mode Dashboard](docs/screenshots/dashboard_dark.png) |

### 🔍 SQLite Live Query Console
![SQLite Live Query Console](docs/screenshots/sql_console.png)

---

## 📊 Dataset Overview

- **Source Collection:** MIT-BIH Arrhythmia Database via PhysioNet (`109,446 records`).
- **Target Classes (AAMI EC57 Standard):**
  - **N:** Normal / Bundle branch block / Escapes
  - **S:** Atrial premature / Supraventricular premature
  - **V:** Premature ventricular contraction / Ventricular escape
  - **F:** Fusion of ventricular and normal
  - **Q:** Paced / Unclassifiable

---

## 🤖 Model Performance Evaluation

Evaluated across macro-averaged metrics to handle class distribution challenges:

| Model Architecture    |  Accuracy  | Precision  |   Recall   |  F1-Score  |
| :-------------------- | :--------: | :--------: | :--------: | :--------: |
| **1D-CNN (Selected)** | **98.20%** | **91.99%** | **90.80%** | **91.38%** |
| **GRU**               |   95.63%   | **93.44%** |   77.44%   |   83.17%   |
| **LSTM**              |   83.86%   |   86.99%   |   60.47%   |   64.97%   |
| **MLP**               |   94.71%   |   90.72%   |   74.79%   |   80.58%   |
| **RNN**               |   23.40%   |   55.75%   |   31.36%   |   22.91%   |

---

## 🛠️ Tech Stack

- **Big Data & Streaming:** Apache Kafka (Local KRaft / Aiven Cloud SSL), Apache Spark, Spark SQL
- **Database & Storage:** SQLite (ACID, WAL mode, auto-indexed), CSV Exports
- **Deep Learning & ML:** TensorFlow, Keras (1D-CNN, GRU, LSTM, RNN, MLP)
- **Frontend & Visualization:** Responsive HTML5 / CSS3 / JavaScript (Chart.js, Flask REST API), Streamlit
- **Infrastructure / Compute:** Kaggle GPUs, Google Colab TPUs, Docker, Docker Compose

---

## 🚀 Quick Start Guide

### 1. Installation

Clone repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Running Unit Tests

Run the full automated test suite covering configuration, Faker metadata, alerting rules, and SQLite query safety:
```bash
python -m unittest discover -s tests -v
```

### 3. Launching Real-time Web Dashboard

#### Option A: Responsive HTML5/CSS3 Web Dashboard (Recommended)
Run the Flask web server:
```bash
cd source_code
python app.py
```
Open your browser at **`http://127.0.0.1:5000`**. Features include:
- **Light & Dark Mode:** Instant 1-click toggle with preference saved in `localStorage`.
- **Live ECG Waveform:** 187 normalized sample points plotted via Chart.js.
- **Health Alert System:** Automatic detection and classification of abnormal beats (`S`, `V`, `F`, `Q`).
- **One-Click Simulator Button:** `⚡ Send Sample Heartbeat` button on the UI to test telemetry and 1D-CNN classification instantly.
- **Embedded SQL Live Query Console:** Query `ecg_pipeline.db` directly in your browser with pre-built query templates.
- **CSV Export:** Download full telemetry records anytime.

#### Option B: Streamlit Dashboard
```bash
cd source_code
streamlit run stream/streamlit_app.py
```

### 4. Running the Streaming Pipeline (Producer & Consumer)

#### Option A: Direct Simulation Mode (Zero Setup - No Kafka needed)
If Kafka is not running, `producer.py` autobmatically detects it and switches to **Direct Stream Simulation Mode**:
```bash
cd source_code
python stream/producer.py
```

#### Option B: Using Local Kafka (Docker)
Start a lightweight local Kafka broker (KRaft mode, no Zookeeper required):
```bash
docker run -d --name kafka-local -p 9092:9092 bashj79/kafka-kraft:latest
```

Then start the consumer and producer:
```bash
# Terminal 1: Consumer (listens to Kafka, classifies with 1D-CNN, writes to SQLite & CSV)
cd source_code
python stream/consumer.py

# Terminal 2: Producer (generates Faker patient metadata & streams ECG signals)
cd source_code
python stream/producer.py
```

#### Option C: Using Aiven Cloud Kafka (SSL Authenticated)
To switch to Aiven Cloud, place your `ca.pem`, `service.cert`, and `service.key` into `source_code/stream/key/` and run:
```bash
$env:USE_LOCAL_KAFKA="false"    # Windows PowerShell
export USE_LOCAL_KAFKA=false     # Linux / MacOS
```

### 5. Running with Docker Compose

Deploy the entire end-to-end pipeline (Local Kafka + Producer + Consumer + Web Dashboard):
```bash
docker compose up --build
```

