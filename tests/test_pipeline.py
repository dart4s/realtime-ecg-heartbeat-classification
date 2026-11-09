"""
Unit tests for the Real-time ECG Heartbeat Classification Pipeline.

Tests pure functions that don't require live Kafka/TensorFlow connections:
  • Label mapping and descriptions
  • Patient metadata generation (Faker)
  • Health alert generation
  • CSV reading / writing helpers
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add stream directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "source_code", "stream"))

from config import (
    ALERT_CLASSES,
    ALERT_SEVERITY,
    ECG_SIGNAL_LENGTH,
    LABEL_DESCRIPTIONS,
    LABEL_MAP,
    NUM_CLASSES,
)
from producer import generate_patient_metadata
from streamlit_app import generate_health_alerts
import pandas as pd


class TestConfig(unittest.TestCase):
    """Test configuration constants and mappings."""

    def test_num_classes(self):
        self.assertEqual(NUM_CLASSES, 5)
        self.assertEqual(len(LABEL_MAP), 5)
        self.assertEqual(len(LABEL_DESCRIPTIONS), 5)

    def test_label_map_keys(self):
        expected_labels = {0: "N", 1: "S", 2: "V", 3: "F", 4: "Q"}
        self.assertEqual(LABEL_MAP, expected_labels)

    def test_alert_classes(self):
        # Normal class 'N' should NOT trigger alerts
        self.assertNotIn("N", ALERT_CLASSES)
        # All abnormal classes must trigger alerts
        self.assertEqual(ALERT_CLASSES, {"S", "V", "F", "Q"})

    def test_alert_severity_coverage(self):
        # Every alert class must have a defined severity level
        for cls in ALERT_CLASSES:
            self.assertIn(cls, ALERT_SEVERITY)
            self.assertIn("level", ALERT_SEVERITY[cls])
            self.assertIn("description", ALERT_SEVERITY[cls])

    def test_signal_length(self):
        self.assertEqual(ECG_SIGNAL_LENGTH, 187)


class TestDataGeneration(unittest.TestCase):
    """Test synthetic data generation with Faker."""

    def test_patient_metadata_structure(self):
        meta = generate_patient_metadata()
        required_keys = [
            "Patient ID",
            "Patient Name",
            "Age",
            "Gender",
            "Hospital Name",
            "Hospital Address",
        ]
        for key in required_keys:
            self.assertIn(key, meta)

    def test_patient_age_range(self):
        for _ in range(50):
            meta = generate_patient_metadata()
            self.assertGreaterEqual(meta["Age"], 18)
            self.assertLessEqual(meta["Age"], 95)

    def test_patient_gender_values(self):
        for _ in range(50):
            meta = generate_patient_metadata()
            self.assertIn(meta["Gender"], ("Male", "Female"))

    def test_unique_patient_ids(self):
        ids = {generate_patient_metadata()["Patient ID"] for _ in range(100)}
        self.assertEqual(len(ids), 100)


class TestHealthAlerts(unittest.TestCase):
    """Test health alert generation in the dashboard."""

    def test_empty_dataframe(self):
        alerts = generate_health_alerts(pd.DataFrame())
        self.assertEqual(alerts, [])

    def test_no_abnormal_records(self):
        df = pd.DataFrame({
            "Time": ["12:00:00", "12:00:03"],
            "Result": ["N", "N"],
            "Patient Name": ["John Doe", "Jane Doe"],
            "Hospital Name": ["General", "General"],
        })
        alerts = generate_health_alerts(df)
        self.assertEqual(alerts, [])

    def test_abnormal_records_trigger_alerts(self):
        df = pd.DataFrame({
            "Time": ["12:00:00", "12:00:03", "12:00:06"],
            "Result": ["N", "V", "S"],
            "Patient Name": ["John", "Alice", "Bob"],
            "Hospital Name": ["H1", "H2", "H3"],
        })
        alerts = generate_health_alerts(df)
        self.assertEqual(len(alerts), 2)
        # Most recent first
        self.assertEqual(alerts[0]["result"], "S")
        self.assertEqual(alerts[0]["patient_name"], "Bob")
        self.assertEqual(alerts[1]["result"], "V")
        self.assertEqual(alerts[1]["patient_name"], "Alice")

    def test_max_alerts_limit(self):
        df = pd.DataFrame({
            "Time": [f"12:00:{i:02d}" for i in range(20)],
            "Result": ["V"] * 20,
            "Patient Name": [f"Patient_{i}" for i in range(20)],
            "Hospital Name": ["H"] * 20,
        })
        alerts = generate_health_alerts(df, max_alerts=5)
        self.assertEqual(len(alerts), 5)


class TestDatabase(unittest.TestCase):
    """Test SQLite database operations and safety checks."""

    def setUp(self):
        self.test_db = os.path.join(os.path.dirname(__file__), "test_temp.db")
        from database import init_db
        init_db(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_insert_and_query_record(self):
        from database import insert_telemetry_record, get_recent_records
        rec = {
            "Time": "10/11/2026 12:00:00",
            "Patient ID": "TEST01",
            "Patient Name": "Unit Test Patient",
            "Age": 45,
            "Gender": "Male",
            "Hospital Name": "Test Hospital",
            "Result": "V",
            "ECG Heartbeat": [0.1] * 187,
        }
        row_id = insert_telemetry_record(rec, db_path=self.test_db)
        self.assertGreater(row_id, 0)

        records = get_recent_records(limit=5, db_path=self.test_db)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Patient Name"], "Unit Test Patient")
        self.assertEqual(records[0]["Result"], "V")

    def test_sql_console_safety(self):
        from database import execute_custom_query
        # Read query should succeed
        res_ok = execute_custom_query("SELECT COUNT(*) FROM telemetry_records;", db_path=self.test_db)
        self.assertEqual(res_ok["status"], "success")

        # Write/Drop query should be blocked
        res_drop = execute_custom_query("DROP TABLE telemetry_records;", db_path=self.test_db)
        self.assertEqual(res_drop["status"], "error")
        self.assertIn("read-only", res_drop["message"])


if __name__ == "__main__":
    unittest.main()
