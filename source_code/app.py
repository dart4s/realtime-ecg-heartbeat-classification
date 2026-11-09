"""
Flask Web Dashboard for Real-time ECG Heartbeat Monitoring.
Replaces Streamlit with a lightweight, responsive HTML/CSS/JavaScript interface.

Features:
  - Serves static HTML/CSS/JS frontend
  - Real-time JSON API endpoints for ECG telemetry, KPIs, Health Alerts, and Trends
  - Interactive Chart.js for real-time waveform and distribution visualization
  - Hospital-based record filtering and CSV data export
"""

import ast
import json
import os
import sys
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, render_template, request, Response

# Ensure stream module is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "stream"))
from config import (
    ALERT_CLASSES,
    ALERT_SEVERITY,
    HOSPITAL_DATA_PATH,
    LABEL_DESCRIPTIONS,
    LABEL_MAP,
    RECEIVED_DATA_PATH,
    TRAIN_DATA_PATH,
)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_train_counts():
    if os.path.exists(TRAIN_DATA_PATH):
        try:
            train = pd.read_csv(TRAIN_DATA_PATH, header=None)
            counts = train[187].value_counts()
            return {
                "total": int(train.shape[0]),
                "N": int(counts.get(0, 0)),
                "S": int(counts.get(1, 0)),
                "V": int(counts.get(2, 0)),
                "F": int(counts.get(3, 0)),
                "Q": int(counts.get(4, 0)),
            }
        except Exception:
            pass
    return {"total": 0, "N": 0, "S": 0, "V": 0, "F": 0, "Q": 0}

def load_stream_records():
    if not os.path.exists(RECEIVED_DATA_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(RECEIVED_DATA_PATH)
        return df
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Main dashboard page."""
    hospitals = ["All Hospitals"]
    if os.path.exists(HOSPITAL_DATA_PATH):
        try:
            h_df = pd.read_csv(HOSPITAL_DATA_PATH)
            hospitals += list(h_df["OrganisationName"].dropna().unique())
        except Exception:
            pass
    return render_template("index.html", hospitals=hospitals, label_info=LABEL_DESCRIPTIONS)


@app.route("/api/telemetry")
def api_telemetry():
    """API endpoint providing real-time data, metrics, alerts, and ECG waveform from SQLite."""
    hospital_filter = request.args.get("hospital", "All Hospitals")
    from database import (
        get_telemetry_kpis,
        get_recent_alerts,
        get_latest_ecg,
        get_recent_records,
        get_trend_data,
    )

    db_kpis = get_telemetry_kpis(hospital=hospital_filter)
    train_counts = get_train_counts()

    kpis = {
        "total": train_counts["total"] + db_kpis["stream_total"],
        "stream_total": db_kpis["stream_total"],
        "N": train_counts["N"] + db_kpis["N"],
        "S": train_counts["S"] + db_kpis["S"],
        "V": train_counts["V"] + db_kpis["V"],
        "F": train_counts["F"] + db_kpis["F"],
        "Q": train_counts["Q"] + db_kpis["Q"],
    }

    alerts = get_recent_alerts(limit=10)
    latest_ecg = get_latest_ecg()
    recent_records = get_recent_records(limit=25, hospital=hospital_filter)
    trend_data = get_trend_data()

    return jsonify({
        "status": "active" if db_kpis["stream_total"] > 0 else "waiting",
        "kpis": kpis,
        "alerts": alerts,
        "distribution": {
            "N": db_kpis["N"],
            "S": db_kpis["S"],
            "V": db_kpis["V"],
            "F": db_kpis["F"],
            "Q": db_kpis["Q"],
        },
        "trend": trend_data,
        "latest_ecg": latest_ecg,
        "records": recent_records,
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    })


@app.route("/api/export-csv")
def api_export_csv():
    """Download full records as CSV directly exported from SQLite."""
    from database import export_records_dataframe
    df = export_records_dataframe()
    csv_bytes = df.to_csv(index=False)
    filename = f"ecg_telemetry_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


@app.route("/api/query", methods=["POST"])
def api_query():
    """Execute a custom safe read-only SQL query against the SQLite database."""
    data = request.get_json() or {}
    sql = data.get("query", "").strip()
    if not sql:
        return jsonify({"status": "error", "message": "SQL query cannot be empty"}), 400

    from database import execute_custom_query, insert_system_log
    res = execute_custom_query(sql)
    if res.get("status") == "success":
        insert_system_log("WEB_SQL", "INFO", f"Executed query: {sql[:60]}...")
    return jsonify(res)


@app.route("/api/logs")
def api_logs():
    """Fetch recent system logs for monitoring."""
    from database import get_system_logs
    limit = int(request.args.get("limit", 30))
    logs = get_system_logs(limit=limit)
    return jsonify({"status": "success", "logs": logs})


_cached_model = None

def get_or_load_model():
    global _cached_model
    if _cached_model is None:
        from consumer import load_model
        _cached_model = load_model()
    return _cached_model


@app.route("/api/simulate-heartbeat", methods=["POST"])
def api_simulate_heartbeat():
    """Trigger a single simulated heartbeat transmission on-demand directly from Web UI."""
    import random
    from producer import generate_patient_metadata
    from consumer import predict, append_to_csv
    from config import STREAM_DATA_PATH

    if not os.path.exists(STREAM_DATA_PATH):
        return jsonify({"status": "error", "message": "Stream data not found"}), 404

    stream_csv = pd.read_csv(STREAM_DATA_PATH)
    idx = random.randint(0, len(stream_csv) - 1)
    row = stream_csv.iloc[idx]

    cur_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ecg_data = row.iloc[:187].values.tolist()
    info_data = row.iloc[188:].to_dict()

    val = {
        "Time": cur_time,
        "ECG Heartbeat": ecg_data,
    }
    val.update(generate_patient_metadata())
    val.update(info_data)

    model = get_or_load_model()
    label = predict(model, ecg_data)
    val["Result"] = label

    from database import insert_telemetry_record, insert_system_log
    insert_telemetry_record(val)
    insert_system_log("WEB_UI", "INFO", f"Simulated heartbeat [{label}] for {val.get('Patient Name', 'Unknown')}")
    append_to_csv(RECEIVED_DATA_PATH, val)

    clean_val = {k: v for k, v in val.items() if k != "ECG Heartbeat"}
    return jsonify({
        "status": "success",
        "record": clean_val,
        "label": label,
    })


if __name__ == "__main__":
    import socket

    # Thử danh sách các cổng thông dụng nếu cổng mặc định bị Windows chiếm dụng/chặn quyền
    preferred_port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    candidate_ports = [preferred_port, 5000, 8080, 8000, 3000, 5050]
    
    selected_port = None
    for p in candidate_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                selected_port = p
                break
            except OSError:
                continue

    if selected_port is None:
        selected_port = preferred_port

    print(f"\n========================================================")
    print(f"🫀 ECG Dashboard Server running at: http://{host}:{selected_port}")
    print(f"========================================================\n")
    
    app.run(host=host, port=selected_port, debug=False)
