"""
SQLite Database Layer for Real-time ECG Heartbeat Telemetry & System Logs.

Provides:
  - ACID-compliant storage with WAL (Write-Ahead Logging) mode for high-concurrency
  - Zero-configuration local database (no external DB server required)
  - Indexed queries for instant KPI calculation, alert filtering, and pagination
  - Structured system logs table for monitoring service health
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

# Setup path to import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ALERT_CLASSES, ALERT_SEVERITY, DB_PATH

logger = logging.getLogger(__name__)


def get_db_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create a database connection with WAL mode and row factory enabled."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency (non-blocking reads while writing)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize database tables and indexes if they do not exist."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Telemetry records table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            patient_id TEXT,
            patient_name TEXT,
            age INTEGER,
            gender TEXT,
            hospital_name TEXT,
            hospital_address TEXT,
            result TEXT NOT NULL,
            is_alert INTEGER DEFAULT 0,
            ecg_signal TEXT
        );
    """)

    # Indexes for lightning-fast queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_time ON telemetry_records (timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_result ON telemetry_records (result);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_hospital ON telemetry_records (hospital_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_alert ON telemetry_records (is_alert);")

    # 2. System logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            service TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_time ON system_logs (timestamp);")

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully at %s (WAL mode enabled)", db_path)


def insert_telemetry_record(record: Dict[str, Any], db_path: str = DB_PATH) -> int:
    """
    Insert a single classified ECG telemetry record into SQLite.
    Returns the inserted record's row ID.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    timestamp = str(record.get("Time") or datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    patient_id = record.get("Patient ID", "")
    patient_name = record.get("Patient Name", "")
    age = record.get("Age")
    gender = record.get("Gender", "")
    hospital_name = record.get("Hospital Name", "")
    hospital_address = record.get("Hospital Address", "")
    result = str(record.get("Result", "N"))

    is_alert = 1 if result in ALERT_CLASSES else 0

    ecg_signal = record.get("ECG Heartbeat")
    if isinstance(ecg_signal, (list, tuple)):
        ecg_json = json.dumps(ecg_signal)
    elif isinstance(ecg_signal, str):
        ecg_json = ecg_signal
    else:
        ecg_json = "[]"

    cursor.execute("""
        INSERT INTO telemetry_records (
            timestamp, patient_id, patient_name, age, gender,
            hospital_name, hospital_address, result, is_alert, ecg_signal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        timestamp, patient_id, patient_name, age, gender,
        hospital_name, hospital_address, result, is_alert, ecg_json
    ))

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def insert_system_log(service: str, level: str, message: str, db_path: str = DB_PATH) -> int:
    """Insert a structured system log into the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cur_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    cursor.execute("""
        INSERT INTO system_logs (timestamp, service, level, message)
        VALUES (?, ?, ?, ?);
    """, (cur_time, service, level, message))

    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_telemetry_kpis(hospital: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, int]:
    """Calculate counts per class and total streamed using instant SQL aggregation."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT result, COUNT(*) as cnt FROM telemetry_records"
    params = []
    if hospital and hospital != "All Hospitals":
        query += " WHERE hospital_name = ?"
        params.append(hospital)
    query += " GROUP BY result;"

    cursor.execute(query, params)
    counts = {"N": 0, "S": 0, "V": 0, "F": 0, "Q": 0}
    total = 0
    for row in cursor.fetchall():
        cls = row["result"]
        cnt = row["cnt"]
        if cls in counts:
            counts[cls] = cnt
        total += cnt

    conn.close()
    return {
        "stream_total": total,
        "N": counts["N"],
        "S": counts["S"],
        "V": counts["V"],
        "F": counts["F"],
        "Q": counts["Q"],
    }


def get_recent_alerts(limit: int = 10, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve the most recent abnormal heartbeat alerts."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, patient_name, hospital_name, result
        FROM telemetry_records
        WHERE is_alert = 1
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))

    alerts = []
    for row in cursor.fetchall():
        res = row["result"]
        sev = ALERT_SEVERITY.get(res, {})
        alerts.append({
            "time": row["timestamp"],
            "patient_name": row["patient_name"] or "Unknown",
            "hospital": row["hospital_name"] or "Unknown",
            "result": res,
            "level": sev.get("level", "Unknown"),
            "description": sev.get("description", ""),
        })

    conn.close()
    return alerts


def get_latest_ecg(db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve the latest heartbeat record including its 187-sample signal."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, patient_name, result, ecg_signal
        FROM telemetry_records
        ORDER BY id DESC
        LIMIT 1;
    """)
    row = cursor.fetchone()
    conn.close()

    if not row or not row["ecg_signal"]:
        return None

    try:
        sig = json.loads(row["ecg_signal"])
        return {
            "signal": [float(x) for x in sig],
            "label": row["result"],
            "patient_name": row["patient_name"] or "N/A",
            "time": row["timestamp"],
        }
    except Exception:
        return None


def get_recent_records(limit: int = 25, hospital: Optional[str] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve recent records (excluding raw signal) for the dashboard table."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    query = """
        SELECT timestamp as Time, patient_id as [Patient ID], patient_name as [Patient Name],
               age as Age, gender as Gender, hospital_name as [Hospital Name],
               hospital_address as [Hospital Address], result as Result
        FROM telemetry_records
    """
    params = []
    if hospital and hospital != "All Hospitals":
        query += " WHERE hospital_name = ?"
        params.append(hospital)
    query += " ORDER BY id DESC LIMIT ?;"
    params.append(limit)

    cursor.execute(query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return records


def get_trend_data(db_path: str = DB_PATH) -> Dict[str, List]:
    """Retrieve progression trend data points for Chart.js."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id, result FROM telemetry_records ORDER BY id ASC;")
    rows = cursor.fetchall()
    conn.close()

    trend = {"labels": [], "N": [], "S": [], "V": [], "F": [], "Q": []}
    if not rows:
        return trend

    total = len(rows)
    step = max(1, total // 30)

    cum = {"N": 0, "S": 0, "V": 0, "F": 0, "Q": 0}
    for idx, row in enumerate(rows, start=1):
        res = row["result"]
        if res in cum:
            cum[res] += 1
        if idx % step == 0 or idx == total:
            trend["labels"].append(f"#{idx}")
            for k in ["N", "S", "V", "F", "Q"]:
                trend[k].append(cum[k])

    return trend


def get_system_logs(limit: int = 50, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve system logs for monitoring."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, service, level, message
        FROM system_logs
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs


def export_records_dataframe(db_path: str = DB_PATH) -> pd.DataFrame:
    """Export all telemetry records (without heavy raw signals) as a DataFrame for CSV download."""
    conn = get_db_connection(db_path)
    df = pd.read_sql_query("""
        SELECT timestamp as Time, patient_id as [Patient ID], patient_name as [Patient Name],
               age as Age, gender as Gender, hospital_name as [Hospital Name],
               hospital_address as [Hospital Address], result as Result
        FROM telemetry_records
        ORDER BY id ASC;
    """, conn)
    conn.close()
    return df


def execute_custom_query(query: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """Execute a safe read-only SQL query and return columns and rows."""
    clean_q = query.strip()
    if not clean_q.upper().startswith(("SELECT", "EXPLAIN", "PRAGMA")):
        return {
            "status": "error",
            "message": "Only read-only queries (SELECT, PRAGMA, EXPLAIN) are allowed in this console.",
        }

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute(clean_q)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [list(row) for row in cursor.fetchall()]
        conn.close()
        return {
            "status": "success",
            "columns": columns,
            "rows": rows,
            "count": len(rows),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
