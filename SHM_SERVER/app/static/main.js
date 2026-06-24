// ============================================================
// main.js — SHM dashboard (v2 per-element API)
// Polls /api/v2/latest + /api/v2/alerts every 5s; loads trend
// history on demand. All values come from the server.
// ============================================================

const POLL_MS = 5000;
const ELEMENTS   = window.__ELEMENTS__ || [];
const THRESHOLDS = window.__THRESHOLDS__ || {};
const DEVICE     = window.__DEVICE__ || null;

const ENV = [
  { key: 'temperature', label: 'Temperature', unit: '°C'   },
  { key: 'humidity',    label: 'Humidity',    unit: '%'    },
  { key: 'vibration',   label: 'Vibration',   unit: 'mm/s' },
  { key: 'sound',       label: 'Sound',       unit: 'dB'   },
];

const LINE_COLORS = ['#2563eb', '#7c3aed', '#0d9488', '#db2777', '#ea580c'];

let strainChart, envChart;
let currentHours = 24;
let alertsMode = 'active';   // 'active' | 'all'

document.addEventListener('DOMContentLoaded', () => {
  if (DEVICE) document.getElementById('device-name').textContent =
    `${DEVICE.name}${DEVICE.location ? ' · ' + DEVICE.location : ''}`;

  buildElementCards();
  buildEnvCards();
  initCharts();
  wireControls();

  refreshLatest();
  refreshAlerts();
  loadHistory(currentHours);
  setInterval(() => { refreshLatest(); refreshAlerts(); }, POLL_MS);
});

// ── Static card scaffolding ──────────────────────────────────
function buildElementCards() {
  const grid = document.getElementById('elements-grid');
  if (!ELEMENTS.length) {
    grid.innerHTML = `<p class="text-sm text-slate-400">No structural elements yet — run <code>flask seed-demo</code>.</p>`;
    return;
  }
  grid.innerHTML = ELEMENTS.map(e => `
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 accent-ok" id="el-card-${e.id}">
      <div class="flex items-center justify-between">
        <div>
          <p class="font-semibold">${e.name}</p>
          <p class="text-xs text-slate-400 capitalize">${e.element_type}</p>
        </div>
        <span class="pill st-ok" id="el-status-${e.id}">OK</span>
      </div>
      <div class="mt-3 flex items-end gap-1">
        <span class="text-3xl font-bold" id="el-value-${e.id}">—</span>
        <span class="text-xs text-slate-400 mb-1">μm/m</span>
      </div>
    </div>`).join('');
}

function buildEnvCards() {
  document.getElementById('env-grid').innerHTML = ENV.map(s => `
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 accent-ok" id="env-card-${s.key}">
      <div class="flex items-center justify-between">
        <p class="text-sm font-medium text-slate-500">${s.label}</p>
        <span class="pill st-ok" id="env-status-${s.key}">OK</span>
      </div>
      <div class="mt-2 flex items-end gap-1">
        <span class="text-2xl font-bold" id="env-value-${s.key}">—</span>
        <span class="text-xs text-slate-400 mb-1">${s.unit}</span>
      </div>
    </div>`).join('');
}

// ── Live snapshot ────────────────────────────────────────────
async function refreshLatest() {
  try {
    const d = await fetchJSON('/api/v2/latest');
    setConnection(true);
    updateHealth(d.health, d.active_alerts);
    updateTimestamp(d.timestamp);
    (d.elements || []).forEach(updateElementCard);
    Object.entries(d.environment || {}).forEach(([k, v]) => updateEnvCard(k, v));
  } catch (err) {
    setConnection(false);
    console.error('latest failed:', err);
  }
}

function updateHealth(health, activeAlerts) {
  document.getElementById('active-alerts-count').textContent = activeAlerts ?? 0;
  if (!health) return;
  const status = labelToStatus(health.label);
  document.getElementById('health-score').textContent = Math.round(health.score);
  document.getElementById('health-label').textContent = health.label;
  document.getElementById('health-sub').textContent =
    status === 'ok' ? 'All monitored signals within safe range'
    : status === 'warning' ? 'One or more signals approaching limits'
    : 'One or more signals beyond critical limits';
  setAccent(document.getElementById('health-card'), status);

  const ring = document.getElementById('health-ring');
  const circ = 327;
  ring.style.strokeDashoffset = circ * (1 - Math.max(0, Math.min(100, health.score)) / 100);
  ring.setAttribute('stroke', statusColor(status));
}

function updateElementCard(e) {
  const v = document.getElementById(`el-value-${e.id}`);
  if (v) v.textContent = e.microstrain == null ? '—' : Number(e.microstrain).toFixed(0);
  setPill(document.getElementById(`el-status-${e.id}`), e.status);
  setAccent(document.getElementById(`el-card-${e.id}`), e.status);
}

function updateEnvCard(key, data) {
  const v = document.getElementById(`env-value-${key}`);
  if (v) v.textContent = data.value == null ? '—' : Number(data.value).toFixed(1);
  setPill(document.getElementById(`env-status-${key}`), data.status);
  setAccent(document.getElementById(`env-card-${key}`), data.status);
}

// ── Alerts ───────────────────────────────────────────────────
async function refreshAlerts() {
  try {
    const active = alertsMode === 'active';
    const alerts = await fetchJSON(`/api/v2/alerts?active=${active}&limit=50`);
    const list = document.getElementById('alerts-list');
    if (!alerts.length) {
      list.innerHTML = `<div class="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
        <span class="dot d-ok"></span> No ${active ? 'active' : ''} alerts — all clear.</div>`;
      return;
    }
    list.innerHTML = alerts.map(alertRow).join('');
  } catch (err) {
    console.error('alerts failed:', err);
  }
}

function alertRow(a) {
  const status = a.severity;
  const when = new Date(a.last_seen || a.timestamp).toLocaleString();
  const scope = a.element ? a.element : 'Device';
  const resolved = a.resolved
    ? `<span class="text-xs text-slate-400">resolved</span>`
    : `<button class="text-xs text-slate-400 hover:text-slate-700" onclick="resolveAlert(${a.id})">Resolve ✕</button>`;
  return `
    <div class="flex items-center justify-between gap-3 border border-slate-200 rounded-lg p-3 accent-${status}">
      <div class="flex items-center gap-3 min-w-0">
        <span class="pill st-${status}">${status.toUpperCase()}</span>
        <div class="min-w-0">
          <p class="text-sm font-medium truncate">${scope} · ${a.message}</p>
          <p class="text-xs text-slate-400">${when}</p>
        </div>
      </div>
      ${resolved}
    </div>`;
}

async function resolveAlert(id) {
  try {
    await fetch(`/api/alerts/${id}/resolve`, { method: 'PATCH' });
    refreshAlerts();
    refreshLatest();
  } catch (err) { console.error('resolve failed:', err); }
}

// ── Charts ───────────────────────────────────────────────────
function initCharts() {
  const base = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
    scales: {
      x: { ticks: { color: '#94a3b8', maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
      y: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { color: '#f1f5f9' } },
    },
  };

  strainChart = new Chart(document.getElementById('strainChart'), {
    type: 'line', data: { labels: [], datasets: [] }, options: base,
  });
  envChart = new Chart(document.getElementById('envChart'), {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      ...base,
      scales: {
        x: base.scales.x,
        y:  { type: 'linear', position: 'left',  ticks: { color: '#ea580c', font: { size: 10 } }, grid: { color: '#f1f5f9' } },
        y1: { type: 'linear', position: 'right', ticks: { color: '#0d9488', font: { size: 10 } }, grid: { display: false } },
      },
    },
  });
}

async function loadHistory(hours) {
  try {
    const d = await fetchJSON(`/api/v2/history?hours=${hours}&max_points=120`);
    const labels = (d.timestamps || []).map(fmtTime);

    // Strain chart: one line per element + warn/crit threshold lines
    const spec = THRESHOLDS.strain || {};
    const datasets = (d.strains || []).map((s, i) => ({
      label: s.name, data: s.values, borderColor: LINE_COLORS[i % LINE_COLORS.length],
      backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true,
    }));
    datasets.push(...thresholdLines(spec, labels.length));
    strainChart.data.labels = labels;
    strainChart.data.datasets = datasets;
    strainChart.update('none');

    // Environment chart: temperature + humidity
    envChart.data.labels = labels;
    envChart.data.datasets = [
      { label: 'Temp (°C)', data: d.series.temperature, borderColor: '#ea580c', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y', spanGaps: true },
      { label: 'Humidity (%)', data: d.series.humidity, borderColor: '#0d9488', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y1', spanGaps: true },
    ];
    envChart.update('none');
  } catch (err) {
    console.error('history failed:', err);
  }
}

function thresholdLines(spec, n) {
  const mk = (val, color, label) => ({
    label, data: Array(n).fill(val), borderColor: color, borderWidth: 1.5,
    borderDash: [6, 4], pointRadius: 0, fill: false, tension: 0,
  });
  const out = [];
  if (spec.warn_high != null) out.push(mk(spec.warn_high, '#f59e0b', 'Warning'));
  if (spec.crit_high != null) out.push(mk(spec.crit_high, '#ef4444', 'Critical'));
  return out;
}

// ── Controls ─────────────────────────────────────────────────
function wireControls() {
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      currentHours = Number(btn.dataset.hours);
      document.querySelectorAll('.range-btn').forEach(b => {
        b.className = 'range-btn px-3 py-1 text-xs rounded-md border border-slate-200 bg-white';
      });
      btn.className = 'range-btn px-3 py-1 text-xs rounded-md border border-slate-900 bg-slate-900 text-white';
      loadHistory(currentHours);
    });
  });

  const active = document.getElementById('alerts-active-btn');
  const all = document.getElementById('alerts-all-btn');
  const on  = 'px-3 py-1 text-xs rounded-md border border-slate-900 bg-slate-900 text-white';
  const off = 'px-3 py-1 text-xs rounded-md border border-slate-200 bg-white';
  active.addEventListener('click', () => { alertsMode = 'active'; active.className = on; all.className = off; refreshAlerts(); });
  all.addEventListener('click',    () => { alertsMode = 'all';    all.className = on; active.className = off; refreshAlerts(); });
}

// ── Helpers ──────────────────────────────────────────────────
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}
function labelToStatus(label) {
  return label === 'Critical' ? 'critical' : label === 'Warning' ? 'warning' : 'ok';
}
function statusColor(s) { return s === 'critical' ? '#ef4444' : s === 'warning' ? '#f59e0b' : '#10b981'; }
function setPill(el, status) {
  if (!el) return;
  el.className = `pill st-${status}`;
  el.textContent = status.toUpperCase();
}
function setAccent(el, status) {
  if (!el) return;
  el.classList.remove('accent-ok', 'accent-warning', 'accent-critical');
  el.classList.add(`accent-${status}`);
}
function setConnection(ok) {
  const dot = document.getElementById('live-dot');
  const txt = document.getElementById('conn-status');
  if (ok) { dot.className = 'dot d-ok live'; txt.textContent = 'Live'; }
  else    { dot.className = 'dot d-critical'; txt.textContent = 'Offline'; }
}
function updateTimestamp(iso) {
  document.getElementById('last-update').textContent = iso ? new Date(iso).toLocaleTimeString() : '—';
}
function fmtTime(iso) {
  const d = new Date(iso);
  return currentHours > 48
    ? d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
