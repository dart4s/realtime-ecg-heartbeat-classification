let ecgChart = null;
let distChart = null;
let trendChart = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initCharts();
  fetchTelemetry();

  // Poll every 3 seconds for real-time updates
  setInterval(fetchTelemetry, 3000);

  document.getElementById("hospitalFilter").addEventListener("change", fetchTelemetry);

  // Bind simulate button
  const btnSimulate = document.getElementById("btnSimulate");
  if (btnSimulate) {
    btnSimulate.addEventListener("click", triggerHeartbeatSimulation);
  }

  // Bind SQL Live Query Console
  const sqlPresets = document.getElementById("sqlPresets");
  const sqlInput = document.getElementById("sqlInput");
  const btnRunQuery = document.getElementById("btnRunQuery");

  if (sqlPresets && sqlInput) {
    sqlPresets.addEventListener("change", () => {
      sqlInput.value = sqlPresets.value;
    });
  }

  if (btnRunQuery) {
    btnRunQuery.addEventListener("click", runSqlQuery);
    // Run default query once on page load
    runSqlQuery();
  }
});

// ============================================================================
// Theme Management (Light / Dark Mode)
// ============================================================================
function initTheme() {
  const savedTheme = localStorage.getItem("ecg_theme") || "light";
  applyTheme(savedTheme);

  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "light" ? "dark" : "light";
      applyTheme(next);
      localStorage.setItem("ecg_theme", next);
      updateChartsTheme(next);
    });
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const themeIcon = document.getElementById("themeIcon");
  const themeText = document.getElementById("themeText");
  if (themeIcon && themeText) {
    if (theme === "dark") {
      themeIcon.innerText = "☀️";
      themeText.innerText = "Light Mode";
    } else {
      themeIcon.innerText = "🌙";
      themeText.innerText = "Dark Mode";
    }
  }
}

function updateChartsTheme(theme) {
  const isDark = theme === "dark";
  const textColor = isDark ? "#8b949e" : "#656d76";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.06)";
  const legendColor = isDark ? "#f0f6fc" : "#1f2328";

  [ecgChart, trendChart].forEach(chart => {
    if (!chart) return;
    chart.options.scales.x.ticks.color = textColor;
    chart.options.scales.x.grid.color = gridColor;
    chart.options.scales.y.ticks.color = textColor;
    chart.options.scales.y.grid.color = gridColor;
    if (chart.options.plugins.legend) {
      chart.options.plugins.legend.labels.color = legendColor;
    }
    chart.update();
  });

  if (distChart && distChart.options.plugins.legend) {
    distChart.options.plugins.legend.labels.color = legendColor;
    distChart.update();
  }
}

// ============================================================================
// Chart.js Initializations
// ============================================================================
function initCharts() {
  const isDark = (document.documentElement.getAttribute("data-theme") || "light") === "dark";
  const textColor = isDark ? "#8b949e" : "#656d76";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.06)";
  const legendColor = isDark ? "#f0f6fc" : "#1f2328";

  // 1. ECG Waveform Chart
  const ctxEcg = document.getElementById("ecgChart").getContext("2d");
  ecgChart = new Chart(ctxEcg, {
    type: "line",
    data: {
      labels: Array.from({ length: 187 }, (_, i) => i),
      datasets: [{
        label: "Normalized Amplitude",
        data: [],
        borderColor: "#0969da",
        backgroundColor: "rgba(9, 105, 218, 0.1)",
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: textColor } },
        y: { grid: { color: gridColor }, ticks: { color: textColor }, min: 0, max: 1 }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });

  // 2. Class Distribution Doughnut Chart
  const ctxDist = document.getElementById("distChart").getContext("2d");
  distChart = new Chart(ctxDist, {
    type: "doughnut",
    data: {
      labels: ["N (Normal)", "S (Supraventricular)", "V (Ventricular)", "F (Fusion)", "Q (Paced/Unknown)"],
      datasets: [{
        data: [0, 0, 0, 0, 0],
        backgroundColor: ["#1a7f37", "#9a6700", "#cf222e", "#8250df", "#0598ab"],
        borderWidth: 1,
        borderColor: isDark ? "#161b22" : "#ffffff"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: legendColor, boxWidth: 12, font: { size: 11 } } }
      }
    }
  });

  // 3. Trend Line Chart
  const ctxTrend = document.getElementById("trendChart").getContext("2d");
  trendChart = new Chart(ctxTrend, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "N", data: [], borderColor: "#1a7f37", borderWidth: 2, pointRadius: 1, tension: 0.1 },
        { label: "S", data: [], borderColor: "#9a6700", borderWidth: 2, pointRadius: 1, tension: 0.1 },
        { label: "V", data: [], borderColor: "#cf222e", borderWidth: 2, pointRadius: 1, tension: 0.1 },
        { label: "F", data: [], borderColor: "#8250df", borderWidth: 2, pointRadius: 1, tension: 0.1 },
        { label: "Q", data: [], borderColor: "#0598ab", borderWidth: 2, pointRadius: 1, tension: 0.1 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: textColor } },
        y: { grid: { color: gridColor }, ticks: { color: textColor } }
      },
      plugins: {
        legend: { labels: { color: legendColor, boxWidth: 10 } }
      }
    }
  });
}

// ============================================================================
// Real-time Telemetry Polling
// ============================================================================
async function fetchTelemetry() {
  const hospital = document.getElementById("hospitalFilter").value;
  try {
    const res = await fetch(`/api/telemetry?hospital=${encodeURIComponent(hospital)}`);
    const data = await res.json();

    document.getElementById("lastUpdate").innerText = `Last updated: ${data.last_update}`;

    // 1. Update KPIs
    document.getElementById("kpiTotal").innerText = data.kpis.total.toLocaleString();
    document.getElementById("kpiStream").innerText = `+${data.kpis.stream_total} streamed`;
    document.getElementById("kpiN").innerText = data.kpis.N.toLocaleString();
    document.getElementById("kpiS").innerText = data.kpis.S.toLocaleString();
    document.getElementById("kpiV").innerText = data.kpis.V.toLocaleString();
    document.getElementById("kpiF").innerText = data.kpis.F.toLocaleString();
    document.getElementById("kpiQ").innerText = data.kpis.Q.toLocaleString();

    // 2. Update Waveform
    if (data.latest_ecg && data.latest_ecg.signal.length > 0) {
      ecgChart.data.datasets[0].data = data.latest_ecg.signal;
      ecgChart.update();
      document.getElementById("waveformTitle").innerText =
        `Heartbeat Waveform [${data.latest_ecg.label}] — Patient: ${data.latest_ecg.patient_name} (${data.latest_ecg.time})`;
    }

    // 3. Update Distribution
    const d = data.distribution;
    distChart.data.datasets[0].data = [d.N, d.S, d.V, d.F, d.Q];
    distChart.update();

    // 4. Update Trend
    if (data.trend && data.trend.labels.length > 0) {
      trendChart.data.labels = data.trend.labels;
      trendChart.data.datasets[0].data = data.trend.N;
      trendChart.data.datasets[1].data = data.trend.S;
      trendChart.data.datasets[2].data = data.trend.V;
      trendChart.data.datasets[3].data = data.trend.F;
      trendChart.data.datasets[4].data = data.trend.Q;
      trendChart.update();
    }

    // 5. Update Health Alerts
    const alertsList = document.getElementById("alertsList");
    if (data.alerts.length === 0) {
      alertsList.innerHTML = `<div class="empty-state">✅ No abnormal heartbeats detected in the recent stream.</div>`;
    } else {
      alertsList.innerHTML = data.alerts.map(a => {
        let cls = "info";
        if (a.result === "V") cls = "critical";
        else if (a.result === "S") cls = "warning";
        else if (a.result === "F") cls = "caution";

        return `
          <div class="alert-item ${cls}">
            <div class="alert-head">
              <span>${a.level}</span>
              <span>${a.time}</span>
            </div>
            <div style="font-weight: 600; margin-bottom: 2px;">
              [${a.result}] ${a.patient_name} (${a.hospital})
            </div>
            <div class="alert-meta">${a.description}</div>
          </div>
        `;
      }).join("");
    }

    // 6. Update Table
    const tableBody = document.getElementById("recordsBody");
    if (data.records.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No records available</td></tr>`;
    } else {
      tableBody.innerHTML = data.records.map(r => `
        <tr>
          <td>${r.Time || "-"}</td>
          <td>${r["Patient ID"] || "-"}</td>
          <td><strong>${r["Patient Name"] || "-"}</strong></td>
          <td>${r.Age || "-"} / ${r.Gender || "-"}</td>
          <td>${r["Hospital Name"] || "-"}</td>
          <td><span class="badge ${r.Result}">${r.Result}</span></td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Failed to fetch telemetry:", err);
  }
}

// ============================================================================
// Trigger Single Simulated Transmission from Browser
// ============================================================================
async function triggerHeartbeatSimulation() {
  const btn = document.getElementById("btnSimulate");
  if (!btn) return;
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerText = "⏳ Sending & Classifying...";

  try {
    const res = await fetch("/api/simulate-heartbeat", { method: "POST" });
    const result = await res.json();
    if (result.status === "success") {
      await fetchTelemetry();
    }
  } catch (err) {
    console.error("Simulation failed:", err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

// ============================================================================
// SQL Console Live Query Execution
// ============================================================================
async function runSqlQuery() {
  const sqlInput = document.getElementById("sqlInput");
  const statusDiv = document.getElementById("queryResultStatus");
  const table = document.getElementById("queryResultTable");
  const thead = document.getElementById("queryResultHead");
  const tbody = document.getElementById("queryResultBody");
  const btnRun = document.getElementById("btnRunQuery");

  if (!sqlInput || !statusDiv || !table) return;

  const query = sqlInput.value.trim();
  if (!query) {
    statusDiv.style.display = "block";
    statusDiv.innerHTML = `<span class="query-error-msg">⚠️ Please enter an SQL query.</span>`;
    return;
  }

  btnRun.disabled = true;
  btnRun.innerText = "⏳ Executing...";
  statusDiv.style.display = "block";
  statusDiv.innerHTML = `<span>Executing query on SQLite...</span>`;

  const startTime = performance.now();
  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query })
    });
    const result = await res.json();
    const duration = (performance.now() - startTime).toFixed(1);

    if (result.status === "success") {
      statusDiv.innerHTML = `<span class="query-success-msg">✅ Query executed in ${duration} ms — ${result.count} row(s) returned.</span>`;

      // Build Table Header
      if (result.columns.length > 0) {
        thead.innerHTML = `<tr>${result.columns.map(c => `<th>${c}</th>`).join("")}</tr>`;
      } else {
        thead.innerHTML = "";
      }

      // Build Table Body
      if (result.rows.length > 0) {
        tbody.innerHTML = result.rows.map(row => {
          return `<tr>${row.map(cell => {
            let val = cell === null ? "<em>NULL</em>" : cell;
            if (typeof val === "string" && val.length > 60 && val.startsWith("[")) {
              val = val.substring(0, 35) + "... [187 points]";
            }
            return `<td>${val}</td>`;
          }).join("")}</tr>`;
        }).join("");
      } else {
        tbody.innerHTML = `<tr><td colspan="${result.columns.length || 1}" style="text-align: center; color: var(--text-muted);">Query returned 0 rows.</td></tr>`;
      }
      table.style.display = "table";
    } else {
      statusDiv.innerHTML = `<span class="query-error-msg">❌ SQL Error: ${result.message}</span>`;
      table.style.display = "none";
    }
  } catch (err) {
    statusDiv.innerHTML = `<span class="query-error-msg">❌ Network Error: Failed to execute query.</span>`;
    table.style.display = "none";
  } finally {
    btnRun.disabled = false;
    btnRun.innerText = "▶️ Execute SQL Query";
  }
}
