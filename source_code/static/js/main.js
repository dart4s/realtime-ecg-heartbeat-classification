let ecgChart = null;
let distChart = null;
let trendChart = null;
let cachedRecords = [];
let lastAlertTimestamp = "";
let lastQueryResult = null;
let audioCtx = null;
let soundEnabled = false;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initSoundAlert();
  initCharts();
  fetchTelemetry();

  // Poll every 3 seconds for real-time updates
  setInterval(fetchTelemetry, 3000);

  document.getElementById("hospitalFilter").addEventListener("change", fetchTelemetry);

  // Search filter for telemetry table
  const searchInput = document.getElementById("telemetrySearch");
  if (searchInput) {
    searchInput.addEventListener("input", renderRecordsTable);
  }

  // Bind simulate button
  const btnSimulate = document.getElementById("btnSimulate");
  if (btnSimulate) {
    btnSimulate.addEventListener("click", triggerHeartbeatSimulation);
  }

  // Bind SQL Live Query Console
  const sqlPresets = document.getElementById("sqlPresets");
  const sqlInput = document.getElementById("sqlInput");
  const btnRunQuery = document.getElementById("btnRunQuery");
  const btnExportCsv = document.getElementById("btnExportQueryCsv");

  if (sqlPresets && sqlInput) {
    sqlPresets.addEventListener("change", () => {
      sqlInput.value = sqlPresets.value;
    });
  }

  if (sqlInput) {
    // Ctrl+Enter or Cmd+Enter to execute query
    sqlInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        runSqlQuery();
      }
    });
  }

  if (btnRunQuery) {
    btnRunQuery.addEventListener("click", runSqlQuery);
    // Run default query once on page load
    runSqlQuery();
  }

  if (btnExportCsv) {
    btnExportCsv.addEventListener("click", exportQueryToCsv);
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

// ============================================================================
// Sound Alert System (Web Audio API Synthesizer)
// ============================================================================
function initSoundAlert() {
  soundEnabled = localStorage.getItem("ecg_sound_enabled") === "true";
  updateSoundButtonUI();

  const soundToggle = document.getElementById("soundToggle");
  if (soundToggle) {
    soundToggle.addEventListener("click", () => {
      soundEnabled = !soundEnabled;
      localStorage.setItem("ecg_sound_enabled", soundEnabled ? "true" : "false");
      updateSoundButtonUI();
      if (soundEnabled) {
        playBeep(880, 0.1, 0.05); // Short audio feedback
      }
    });
  }
}

function updateSoundButtonUI() {
  const icon = document.getElementById("soundIcon");
  const text = document.getElementById("soundText");
  if (!icon || !text) return;
  if (soundEnabled) {
    icon.innerText = "🔔";
    text.innerText = "Sound: On";
  } else {
    icon.innerText = "🔇";
    text.innerText = "Sound: Off";
  }
}

function playBeep(freq, duration, volume = 0.08) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(volume, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + duration);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + duration);
  } catch (e) {
    console.warn("Audio not supported or blocked:", e);
  }
}

function playArrhythmiaAlarm() {
  if (!soundEnabled) return;
  // Subtle medical two-tone chime (880Hz -> 660Hz)
  playBeep(880, 0.12, 0.08);
  setTimeout(() => playBeep(660, 0.18, 0.08), 130);
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

    // 5. Update Health Alerts & Trigger Audio Alarm
    const alertsList = document.getElementById("alertsList");
    if (!data.alerts || data.alerts.length === 0) {
      alertsList.innerHTML = `<div class="empty-state">✅ No abnormal heartbeats detected in the recent stream.</div>`;
    } else {
      const topAlert = data.alerts[0];
      const alertId = `${topAlert.time}_${topAlert.patient_name}_${topAlert.result}`;
      if (alertId !== lastAlertTimestamp) {
        lastAlertTimestamp = alertId;
        if (topAlert.result === "V" || topAlert.result === "F") {
          playArrhythmiaAlarm();
        }
      }

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

    // 6. Update Table Cache & Render
    cachedRecords = data.records || [];
    renderRecordsTable();
  } catch (err) {
    console.error("Failed to fetch telemetry:", err);
  }
}

// ============================================================================
// Render Table with Real-time Search Filtering
// ============================================================================
function renderRecordsTable() {
  const tableBody = document.getElementById("recordsBody");
  if (!tableBody) return;

  const searchInput = document.getElementById("telemetrySearch");
  const query = searchInput ? searchInput.value.trim().toLowerCase() : "";

  let filtered = cachedRecords;
  if (query) {
    filtered = cachedRecords.filter(r => {
      const name = String(r["Patient Name"] || "").toLowerCase();
      const id = String(r["Patient ID"] || "").toLowerCase();
      const hosp = String(r["Hospital Name"] || "").toLowerCase();
      const res = String(r["Result"] || "").toLowerCase();
      return name.includes(query) || id.includes(query) || hosp.includes(query) || res.includes(query);
    });
  }

  if (filtered.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">${query ? "No matching records found for '" + query + "'" : "No records available"}</td></tr>`;
  } else {
    tableBody.innerHTML = filtered.map(r => `
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
// SQL Console Live Query Execution & CSV Export
// ============================================================================
async function runSqlQuery() {
  const sqlInput = document.getElementById("sqlInput");
  const statusDiv = document.getElementById("queryResultStatus");
  const table = document.getElementById("queryResultTable");
  const thead = document.getElementById("queryResultHead");
  const tbody = document.getElementById("queryResultBody");
  const btnRun = document.getElementById("btnRunQuery");
  const btnExportCsv = document.getElementById("btnExportQueryCsv");

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
      lastQueryResult = { columns: result.columns, rows: result.rows };
      statusDiv.innerHTML = `<span class="query-success-msg">✅ Query executed in ${duration} ms — ${result.count} row(s) returned.</span>`;

      if (btnExportCsv) {
        btnExportCsv.style.display = result.count > 0 ? "inline-flex" : "none";
      }

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
      lastQueryResult = null;
      if (btnExportCsv) btnExportCsv.style.display = "none";
      statusDiv.innerHTML = `<span class="query-error-msg">❌ SQL Error: ${result.message}</span>`;
      table.style.display = "none";
    }
  } catch (err) {
    lastQueryResult = null;
    if (btnExportCsv) btnExportCsv.style.display = "none";
    statusDiv.innerHTML = `<span class="query-error-msg">❌ Network Error: Failed to execute query.</span>`;
    table.style.display = "none";
  } finally {
    btnRun.disabled = false;
    btnRun.innerText = "▶️ Execute SQL Query";
  }
}

function exportQueryToCsv() {
  if (!lastQueryResult || !lastQueryResult.columns || lastQueryResult.rows.length === 0) {
    alert("No query results to export.");
    return;
  }
  const cols = lastQueryResult.columns;
  const rows = lastQueryResult.rows;

  const csvRows = [];
  csvRows.push(cols.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","));
  rows.forEach(r => {
    csvRows.push(r.map(cell => {
      const val = cell === null ? "" : String(cell);
      return `"${val.replace(/"/g, '""')}"`;
    }).join(","));
  });

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `query_result_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
