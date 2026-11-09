"""
Streamlit Dashboard — Real-time ECG Heartbeat Classification Monitoring.

Consumes real-time Kafka stream output (CSV) and displays:
  • KPI metrics per AAMI class
  • Patient health alerts for abnormal heartbeats
  • ECG waveform visualization
  • Classification distribution chart
  • Filterable patient records table

Usage (run from source_code/ directory):
    streamlit run stream/streamlit_app.py
"""

import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime
from PIL import Image

import warnings
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Setup — ensure config is importable from the stream/ package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    ALERT_CLASSES,
    ALERT_SEVERITY,
    BANNER_IMAGE_PATH,
    DASHBOARD_REFRESH_SECONDS,
    HOSPITAL_DATA_PATH,
    LABEL_DESCRIPTIONS,
    MAX_DASHBOARD_ALERTS,
    RECEIVED_DATA_PATH,
    TRAIN_DATA_PATH,
)

# ============================================================================
# Helper Functions
# ============================================================================

def plot_ecg_waveform(ecg_data, label, patient_name=""):
    """Plot ECG waveform signal for a given heartbeat."""
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(ecg_data, color="#1f77b4", linewidth=1.0)
    ax.fill_between(range(len(ecg_data)), ecg_data, alpha=0.1, color="#1f77b4")
    ax.set_xlabel("Sample Point", fontsize=10)
    ax.set_ylabel("Amplitude (Normalized)", fontsize=10)
    title = f"ECG Heartbeat Waveform — Classification: [{label}]"
    if patient_name:
        title += f" | Patient: {patient_name}"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlim(0, len(ecg_data) - 1)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def generate_health_alerts(stream_df, max_alerts=MAX_DASHBOARD_ALERTS):
    """Generate patient health alerts for abnormal classifications."""
    alerts = []
    if stream_df.empty:
        return alerts

    abnormal = stream_df[stream_df["Result"].isin(ALERT_CLASSES)]
    if abnormal.empty:
        return alerts

    recent_abnormal = abnormal.tail(max_alerts).iloc[::-1]
    for _, row in recent_abnormal.iterrows():
        result = row["Result"]
        severity = ALERT_SEVERITY.get(result, {})
        alerts.append({
            "time": row.get("Time", "N/A"),
            "patient_name": row.get("Patient Name", "Unknown"),
            "hospital": row.get("Hospital Name", "Unknown"),
            "result": result,
            "level": severity.get("level", "Unknown"),
            "description": severity.get("description", ""),
        })
    return alerts


def plot_class_distribution(stream_df):
    """Plot pie chart of classification distribution for streamed data."""
    if stream_df.empty:
        return None
    counts = stream_df["Result"].value_counts()
    if counts.empty:
        return None

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = ["#2ecc71", "#e74c3c", "#3498db", "#f39c12", "#9b59b6"]
    counts.plot(
        kind="pie", ax=ax, colors=colors[:len(counts)],
        autopct="%1.1f%%", startangle=90, textprops={"fontsize": 10},
    )
    ax.set_ylabel("")
    ax.set_title("Real-time Classification Distribution", fontsize=12, fontweight="bold")
    plt.tight_layout()
    return fig


def plot_trend_chart(stream_df):
    """Plot a cumulative trend line chart of classifications over time."""
    if stream_df.empty or "Time" not in stream_df.columns:
        return None
    try:
        df = stream_df.copy()
        df["idx"] = range(1, len(df) + 1)

        fig, ax = plt.subplots(figsize=(10, 3))
        class_colors = {"N": "#2ecc71", "S": "#e74c3c", "V": "#3498db", "F": "#f39c12", "Q": "#9b59b6"}
        for cls in ["N", "S", "V", "F", "Q"]:
            cumulative = (df["Result"] == cls).cumsum()
            ax.plot(df["idx"], cumulative, label=cls, color=class_colors.get(cls, "#999"), linewidth=1.5)

        ax.set_xlabel("Message #", fontsize=10)
        ax.set_ylabel("Cumulative Count", fontsize=10)
        ax.set_title("Classification Trend Over Time", fontsize=12, fontweight="bold")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        return fig
    except Exception:
        return None


def run_dashboard():
    # ============================================================================
    # Load Static Data
    # ============================================================================
    if os.path.exists(HOSPITAL_DATA_PATH):
        hospital = pd.read_csv(HOSPITAL_DATA_PATH)
    else:
        hospital = pd.DataFrame({"OrganisationName": ["General Hospital", "City Cardio Clinic"]})

    if os.path.exists(TRAIN_DATA_PATH):
        train = pd.read_csv(TRAIN_DATA_PATH, header=None)
        number_label_train = train[187].value_counts()
    else:
        train = pd.DataFrame()
        number_label_train = pd.Series([0, 0, 0, 0, 0], index=[0, 1, 2, 3, 4])

    # ============================================================================
    # Streamlit Page Configuration
    # ============================================================================
    st.set_page_config(
        page_title="ECG Heartbeat Classification",
        page_icon="❤️",
        layout="wide",
    )

    st.title("🫀 Real-time ECG Heartbeat Classification")
    st.markdown(
        "**End-to-end distributed data engineering and deep learning system "
        "for early arrhythmia detection**"
    )

    now = datetime.now()
    dt_string = now.strftime("%d %B %Y %H:%M:%S")
    st.write(f"Last update: {dt_string}")

    if os.path.exists(BANNER_IMAGE_PATH):
        image = Image.open(BANNER_IMAGE_PATH)
        st.image(image)

    st.header("ECG Heartbeat")

    # ============================================================================
    # Filters
    # ============================================================================
    hf = st.checkbox("Filter by hospital name")
    hospital_filter = st.selectbox(
        "Select the Hospital", hospital["OrganisationName"].unique(), disabled=not hf,
    )

    running = True
    stop_button = st.button("Stop streaming")
    placeholder = st.empty()

    # ============================================================================
    # Main Streaming Loop
    # ============================================================================
    while running:
        if stop_button:
            st.write("Streaming stopped.")
            break

        try:
            stream = pd.read_csv(RECEIVED_DATA_PATH).drop("ECG Heartbeat", axis=1)
        except (FileNotFoundError, pd.errors.EmptyDataError, KeyError):
            st.info("⏳ Waiting for data… Ensure the Kafka consumer (consumer.py) is running.")
            time.sleep(DASHBOARD_REFRESH_SECONDS)
            continue

        with placeholder.container():

            # ================================================================
            # KPI Metrics
            # ================================================================
            st.subheader("📊 Key Performance Indicators")
            kpi, kpi0, kpi1, kpi2, kpi3, kpi4 = st.columns(6)

            kpi.metric(
                label="Total Patients",
                value=train.shape[0] + stream.shape[0],
                delta=stream.shape[0],
            )
            kpi0.metric(
                label="[N] Normal",
                value=number_label_train[0] + len(stream[stream["Result"] == "N"]),
                delta=len(stream[stream["Result"] == "N"]),
            )
            kpi1.metric(
                label="[S] Supraventricular",
                value=number_label_train[1] + len(stream[stream["Result"] == "S"]),
                delta=len(stream[stream["Result"] == "S"]),
            )
            kpi2.metric(
                label="[V] Ventricular",
                value=number_label_train[2] + len(stream[stream["Result"] == "V"]),
                delta=len(stream[stream["Result"] == "V"]),
            )
            kpi3.metric(
                label="[F] Fusion",
                value=number_label_train[3] + len(stream[stream["Result"] == "F"]),
                delta=len(stream[stream["Result"] == "F"]),
            )
            kpi4.metric(
                label="[Q] Paced/Unknown",
                value=number_label_train[4] + len(stream[stream["Result"] == "Q"]),
                delta=len(stream[stream["Result"] == "Q"]),
            )

            st.markdown("---")

            # ================================================================
            # Health Alerts
            # ================================================================
            st.subheader("🚨 Patient Health Alerts")
            alerts = generate_health_alerts(stream)

            if alerts:
                for alert in alerts:
                    with st.expander(
                        f"{alert['level']} — {alert['patient_name']} at {alert['time']}"
                    ):
                        st.write(f"**Patient:** {alert['patient_name']}")
                        st.write(f"**Hospital:** {alert['hospital']}")
                        st.write(f"**Classification:** [{alert['result']}] — {alert['description']}")
                        st.write(f"**Time:** {alert['time']}")
            else:
                st.success("✅ No abnormal heartbeats detected in the current stream.")

            st.markdown("---")

            # ================================================================
            # ECG Waveform Visualization
            # ================================================================
            st.subheader("📈 Latest ECG Waveform")
            try:
                full_stream = pd.read_csv(RECEIVED_DATA_PATH)
                if not full_stream.empty and "ECG Heartbeat" in full_stream.columns:
                    latest_row = full_stream.iloc[-1]
                    ecg_raw = latest_row["ECG Heartbeat"]
                    if isinstance(ecg_raw, str):
                        ecg_values = [float(x.strip()) for x in ecg_raw.strip("[]").split(",")]
                    else:
                        ecg_values = [float(ecg_raw)]

                    latest_label = latest_row.get("Result", "N/A")
                    patient_name = latest_row.get("Patient Name", "")
                    fig = plot_ecg_waveform(ecg_values, latest_label, patient_name)
                    st.pyplot(fig)
                    plt.close(fig)
            except Exception:
                st.info("ECG waveform visualization will appear when data is available.")

            st.markdown("---")

            # ================================================================
            # Classification Distribution & Trend
            # ================================================================
            col_chart, col_table = st.columns(2)

            with col_chart:
                st.subheader("📊 Classification Distribution")
                dist_fig = plot_class_distribution(stream)
                if dist_fig:
                    st.pyplot(dist_fig)
                    plt.close(dist_fig)

            with col_table:
                st.subheader("📋 AAMI EC57 Standard Classes")
                class_info = pd.DataFrame({
                    "Code": LABEL_DESCRIPTIONS.keys(),
                    "Description": LABEL_DESCRIPTIONS.values(),
                })
                st.table(class_info)

            st.markdown("---")

            # ================================================================
            # Historical Trend Chart
            # ================================================================
            st.subheader("📉 Classification Trend Over Time")
            trend_fig = plot_trend_chart(stream)
            if trend_fig:
                st.pyplot(trend_fig)
                plt.close(trend_fig)
            else:
                st.info("Trend chart will appear after data starts streaming.")

            st.markdown("---")

            # ================================================================
            # Data Table with Export
            # ================================================================
            st.subheader("📄 Patient Records")

            if hf:
                df = stream[stream["Hospital Name"] == hospital_filter]
            else:
                df = stream

            st.dataframe(df, use_container_width=True)

            # Export button
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Export to CSV",
                data=csv_data,
                file_name=f"ecg_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

        time.sleep(DASHBOARD_REFRESH_SECONDS)

if __name__ == "__main__":
    run_dashboard()
