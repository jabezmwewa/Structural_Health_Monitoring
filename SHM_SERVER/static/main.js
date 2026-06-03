// ============================================================
// main.js  –  SHM Dashboard live data polling
// ============================================================
// Replaces all mock-data functions from the original template.
// Flask injects `window.__INITIAL_DATA__` on first load so charts
// render immediately; after that, this file polls every 5 seconds.
// ============================================================

const POLL_INTERVAL_MS = 5000;

let vibrationChart;
let tempHumidityChart;

// ── Bootstrap ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initCharts(window.__INITIAL_DATA__ || []);
  poll();                              // first fetch immediately
  setInterval(poll, POLL_INTERVAL_MS);
  setInterval(updateTimestamp, 1000);
});


// ── Polling ──────────────────────────────────────────────────

async function poll() {
  try {
    const [latest, alerts] = await Promise.all([
      fetchJSON('/api/latest'),
      fetchJSON('/api/alerts'),
    ]);
    updateMetricCards(latest);
    updateAlertPanel(alerts);
    pushChartPoint(latest);
  } catch (err) {
    console.error('Poll failed:', err);
  }
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}


// ── Metric Cards ─────────────────────────────────────────────

function updateMetricCards(reading) {
  setCard('vibration',   reading.vibration,   'mm/s');
  setCard('strain',      reading.strain,      'μm/m');
  setCard('temperature', reading.temperature, '°C');
  setCard('humidity',    reading.humidity,    '%');
  setCard('pressure',    reading.pressure,    'kPa');
}

function setCard(id, value, unit) {
  const el = document.getElementById(`${id}-value`);
  if (!el || value == null) return;
  el.textContent = parseFloat(value).toFixed(2);
  // retrigger CSS animation
  el.classList.remove('data-value');
  void el.offsetWidth;
  el.classList.add('data-value');
}


// ── Alert Panel ──────────────────────────────────────────────

function updateAlertPanel(alerts) {
  const container = document.getElementById('alerts-container');
  if (!container) return;

  if (!alerts.length) {
    container.innerHTML = allClearHTML();
    return;
  }

  container.innerHTML = alerts.map(alertCardHTML).join('');
}

function allClearHTML() {
  return `
    <div class="bg-green-500/10 border border-green-500/30 p-4 rounded flex items-start space-x-3">
      <svg class="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9
             10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
          clip-rule="evenodd"/>
      </svg>
      <div>
        <p class="text-sm font-semibold">System Status: All Clear</p>
        <p class="text-xs text-gray-400 mt-1">No active anomalies detected</p>
      </div>
    </div>`;
}

function alertCardHTML(alert) {
  const isCritical = alert.severity === 'critical';
  const colour     = isCritical ? 'red' : 'yellow';
  const icon       = isCritical ? '🔴' : '⚠️';
  return `
    <div class="bg-${colour}-500/10 border border-${colour}-500/30 p-4 rounded flex items-start space-x-3">
      <span class="text-xl">${icon}</span>
      <div class="flex-1">
        <p class="text-sm font-semibold">${alert.message}</p>
        <p class="text-xs text-gray-400 mt-1">${new Date(alert.timestamp).toLocaleTimeString()}</p>
      </div>
      <button
        class="text-${colour}-400 hover:text-${colour}-300 transition"
        onclick="resolveAlert(${alert.id}, this)">✕</button>
    </div>`;
}

async function resolveAlert(id, btn) {
  try {
    await fetch(`/api/alerts/${id}/resolve`, { method: 'PATCH' });
    btn.closest('div.flex').remove();
  } catch (err) {
    console.error('Resolve failed:', err);
  }
}


// ── Charts ───────────────────────────────────────────────────

function initCharts(history) {
  const labels  = history.map(r => formatTime(r.timestamp));
  const vibData = history.map(r => r.vibration ?? 0);
  const tmpData = history.map(r => r.temperature);
  const humData = history.map(r => r.humidity);

  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#d1d5db', font: { size: 12 } } } },
    scales: {
      x: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(75,85,99,.2)' } },
      y: { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(75,85,99,.2)' } },
    },
  };

  // Vibration chart
  const vCtx = document.getElementById('vibrationChart');
  if (vCtx) {
    vibrationChart = new Chart(vCtx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Vibration (mm/s)',
          data: vibData,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,.1)',
          tension: 0.4, fill: true, borderWidth: 2,
          pointRadius: 0, pointHoverRadius: 6,
        }],
      },
      options: baseOptions,
    });
  }

  // Temp + humidity chart
  const thCtx = document.getElementById('tempHumidityChart');
  if (thCtx) {
    tempHumidityChart = new Chart(thCtx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Temperature (°C)',
            data: tmpData,
            borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,.1)',
            tension: 0.4, fill: true, borderWidth: 2,
            pointRadius: 0, yAxisID: 'y',
          },
          {
            label: 'Humidity (%)',
            data: humData,
            borderColor: '#14b8a6', backgroundColor: 'rgba(20,184,166,.1)',
            tension: 0.4, fill: true, borderWidth: 2,
            pointRadius: 0, yAxisID: 'y1',
          },
        ],
      },
      options: {
        ...baseOptions,
        scales: {
          x:  { ticks: { color: '#9ca3af' }, grid: { color: 'rgba(75,85,99,.2)' } },
          y:  { type: 'linear', position: 'left',  ticks: { color: '#f97316' }, grid: { color: 'rgba(75,85,99,.2)' } },
          y1: { type: 'linear', position: 'right', ticks: { color: '#14b8a6' }, grid: { drawOnChartArea: false } },
        },
      },
    });
  }
}

/** Appends the latest reading to both charts, keeping max 48 points. */
function pushChartPoint(reading) {
  const MAX_POINTS = 48;
  const label = formatTime(reading.timestamp);

  [vibrationChart, tempHumidityChart].forEach(chart => {
    if (!chart) return;
    chart.data.labels.push(label);
    if (chart.data.labels.length > MAX_POINTS) chart.data.labels.shift();
  });

  if (vibrationChart) {
    const ds = vibrationChart.data.datasets[0];
    ds.data.push(reading.vibration ?? 0);
    if (ds.data.length > MAX_POINTS) ds.data.shift();
    vibrationChart.update('none');
  }

  if (tempHumidityChart) {
    tempHumidityChart.data.datasets[0].data.push(reading.temperature);
    tempHumidityChart.data.datasets[1].data.push(reading.humidity);
    tempHumidityChart.data.datasets.forEach(ds => {
      if (ds.data.length > MAX_POINTS) ds.data.shift();
    });
    tempHumidityChart.update('none');
  }
}


// ── Helpers ──────────────────────────────────────────────────

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function updateTimestamp() {
  const el = document.getElementById('last-update');
  if (el) el.textContent = new Date().toLocaleTimeString();
}
