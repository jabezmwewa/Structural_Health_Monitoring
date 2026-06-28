// ============================================================
// main.js — SHM dashboard
// Polls /api/v2/latest + /api/v2/alerts every 5 s; loads trend
// history on demand. Fetches Open-Meteo weather every 10 min.
// ECharts: health gauge + strain distribution bar chart.
// Chart.js: strain trend + env trend time-series.
// ============================================================

const POLL_MS      = 5000;
const WEATHER_MS   = 600_000;   // 10 min
const ELEMENTS     = window.__ELEMENTS__   || [];
const THRESHOLDS   = window.__THRESHOLDS__ || {};
const DEVICE       = window.__DEVICE__     || null;

const ENV_SENSORS = [
  { key: 'temperature', label: 'Temperature', unit: '°C'   },
  { key: 'humidity',    label: 'Humidity',    unit: '%'    },
  { key: 'vibration',   label: 'Vibration',   unit: 'mm/s' },
  { key: 'sound',       label: 'Sound',       unit: 'dB'   },
];

const LINE_COLORS = ['#2563eb', '#7c3aed', '#0d9488', '#db2777', '#ea580c'];

// ── WMO weather codes ────────────────────────────────────────
const WMO_DESC = {
  0:'Clear sky', 1:'Mainly clear', 2:'Partly cloudy', 3:'Overcast',
  45:'Fog', 48:'Icy fog',
  51:'Light drizzle', 53:'Drizzle', 55:'Heavy drizzle',
  61:'Light rain', 63:'Moderate rain', 65:'Heavy rain',
  71:'Light snow', 73:'Moderate snow', 75:'Heavy snow', 77:'Snow grains',
  80:'Light showers', 81:'Moderate showers', 82:'Violent showers',
  85:'Snow showers', 86:'Heavy snow showers',
  95:'Thunderstorm', 96:'Thunderstorm + hail', 99:'Heavy thunderstorm',
};
const WMO_ICON = {
  0:'☀️', 1:'🌤️', 2:'⛅', 3:'☁️',
  45:'🌫️', 48:'🌫️',
  51:'🌦️', 53:'🌦️', 55:'🌧️',
  61:'🌧️', 63:'🌧️', 65:'🌧️',
  71:'🌨️', 73:'❄️', 75:'❄️', 77:'❄️',
  80:'🌦️', 81:'🌧️', 82:'⛈️',
  85:'🌨️', 86:'❄️',
  95:'⛈️', 96:'⛈️', 99:'⛈️',
};

// ── Module-level state ────────────────────────────────────────
let strainChart, envChart;
let healthGauge, strainDistChart;
let currentHours  = 24;
let alertsMode    = 'active';
let latestElements = [];   // cache for strain-dist chart updates
let currentScore   = 0;
let currentLabel   = '—';

// ── Dark mode ─────────────────────────────────────────────────
function isDark() {
  return document.documentElement.classList.contains('dark');
}

function applyDark(dark) {
  document.documentElement.classList.toggle('dark', dark);
  document.getElementById('icon-moon').classList.toggle('hidden', dark);
  document.getElementById('icon-sun').classList.toggle('hidden', !dark);
  // Re-render ECharts so their text/grid colors update.
  updateGauge(currentScore, currentLabel);
  updateStrainDist(latestElements);
  updateChartsForDark();
}

function toggleDark() {
  const next = !isDark();
  localStorage.setItem('shm-dark', next);
  applyDark(next);
}

function initDarkMode() {
  const saved = localStorage.getItem('shm-dark');
  const sys   = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyDark(saved !== null ? saved === 'true' : sys);
}

// ── Sidebar ───────────────────────────────────────────────────
function toggleSidebar() {
  const s = document.getElementById('sidebar');
  const b = document.getElementById('sidebar-backdrop');
  const open = !s.classList.contains('-translate-x-full');
  s.classList.toggle('-translate-x-full', open);
  b.classList.toggle('hidden', open);
}
function closeSidebar() {
  document.getElementById('sidebar').classList.add('-translate-x-full');
  document.getElementById('sidebar-backdrop').classList.add('hidden');
}

// ── ECharts: health gauge ─────────────────────────────────────
function gaugeOption(score, label) {
  const grey  = '#94a3b8';
  const dark  = isDark();
  return {
    backgroundColor: 'transparent',
    series: [{
      type: 'gauge',
      startAngle: 210,
      endAngle: -30,
      radius: '90%',
      center: ['50%', '56%'],
      min: 0, max: 100,
      splitNumber: 4,
      axisLine: {
        lineStyle: {
          width: 16,
          color: [[0.3, '#ef4444'], [0.6, '#f59e0b'], [1, '#10b981']],
        },
      },
      pointer: {
        length: '68%', width: 7,
        offsetCenter: [0, '-4%'],
        itemStyle: { color: 'auto' },
      },
      axisTick:  { length: 8,  lineStyle: { color: 'auto', width: 2 } },
      splitLine: { length: 16, lineStyle: { color: 'auto', width: 4 } },
      axisLabel: { color: grey, fontSize: 10, distance: -40 },
      title:     { fontSize: 11, color: grey, offsetCenter: [0, '42%'] },
      detail: {
        valueAnimation: true,
        fontSize: 30,
        fontWeight: 'bold',
        formatter: '{value}',
        color: 'auto',
        offsetCenter: [0, '22%'],
      },
      data: [{ value: Math.round(score ?? 0), name: label ?? '—' }],
    }],
  };
}

function initGauge() {
  const el = document.getElementById('health-gauge');
  if (!el || typeof echarts === 'undefined') return;
  healthGauge = echarts.init(el, null, { renderer: 'svg' });
  healthGauge.setOption(gaugeOption(0, '—'));
}

function updateGauge(score, label) {
  if (!healthGauge) return;
  healthGauge.setOption(gaugeOption(score, label));
}

// ── ECharts: strain distribution bar chart ────────────────────
function strainDistOption(names, values, statuses) {
  const dark     = isDark();
  const txtColor = dark ? '#94a3b8' : '#64748b';
  const gridClr  = dark ? '#334155' : '#f1f5f9';
  const warn     = (THRESHOLDS.strain || {}).warn_high ?? 400;
  const crit     = (THRESHOLDS.strain || {}).crit_high ?? 500;
  const maxVal   = Math.max(crit * 1.1, ...(values.map(v => v ?? 0)));

  return {
    backgroundColor: 'transparent',
    grid: { left: 10, right: 70, top: 8, bottom: 20, containLabel: true },
    xAxis: {
      type: 'value',
      max: Math.ceil(maxVal / 100) * 100,
      axisLabel: { formatter: '{value}', color: txtColor, fontSize: 10 },
      splitLine: { lineStyle: { color: gridClr } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: { color: txtColor, fontSize: 11 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: gridClr } },
    },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({
        value: v ?? 0,
        itemStyle: {
          color: statusColor(statuses[i] ?? 'ok'),
          borderRadius: [0, 4, 4, 0],
        },
      })),
      label: {
        show: true,
        position: 'right',
        formatter: p => p.value > 0 ? `${p.value} μm/m` : '—',
        color: txtColor,
        fontSize: 10,
      },
      barMaxWidth: 26,
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 1.5 },
        label: { fontSize: 10, position: 'insideStartTop' },
        data: [
          { xAxis: warn, lineStyle: { color: '#f59e0b' }, label: { formatter: `${warn} ⚠`, color: '#b45309' } },
          { xAxis: crit, lineStyle: { color: '#ef4444' }, label: { formatter: `${crit} 🔴`, color: '#b91c1c' } },
        ],
      },
    }],
  };
}

function initStrainDist() {
  const el = document.getElementById('strain-dist-chart');
  if (!el || typeof echarts === 'undefined') return;
  strainDistChart = echarts.init(el, null, { renderer: 'svg' });
}

function updateStrainDist(elements) {
  if (!strainDistChart || !elements.length) return;
  const names    = elements.map(e => e.name);
  const values   = elements.map(e => e.microstrain != null ? Number(e.microstrain).toFixed(0) * 1 : 0);
  const statuses = elements.map(e => e.status ?? 'ok');
  strainDistChart.setOption(strainDistOption(names, values, statuses));
}

// ── Entry point ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDarkMode();

  if (DEVICE) {
    const label = `${DEVICE.name}${DEVICE.location ? ' · ' + DEVICE.location : ''}`;
    document.getElementById('device-name').textContent   = label;
    document.getElementById('sidebar-device').textContent = label;
  }

  buildElementCards();
  initGauge();
  initStrainDist();
  initCharts();
  wireControls();

  refreshLatest();
  refreshAlerts();
  refreshAnalysis();
  refreshWeather();
  loadHistory(currentHours);

  setInterval(() => { refreshLatest(); refreshAlerts(); }, POLL_MS);
  setInterval(refreshAnalysis, 30_000);
  setInterval(refreshWeather,  WEATHER_MS);

  window.addEventListener('resize', () => {
    healthGauge?.resize();
    strainDistChart?.resize();
  });
});

// ── Card scaffolding ──────────────────────────────────────────
function buildElementCards() {
  const grid = document.getElementById('elements-grid');
  if (!ELEMENTS.length) {
    grid.innerHTML = `<p class="text-sm text-slate-400 col-span-3">
      No structural elements yet — run <code>flask seed-demo</code>.</p>`;
    return;
  }
  grid.innerHTML = ELEMENTS.map(e => `
    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-2xl
                border border-slate-200 dark:border-slate-600
                p-4 accent-ok" id="el-card-${e.id}">
      <div class="flex items-start justify-between">
        <div>
          <p class="font-semibold text-sm">${e.name}</p>
          <p class="text-[11px] text-slate-400 capitalize mt-0.5">${e.element_type}</p>
        </div>
        <span class="pill st-ok" id="el-status-${e.id}">OK</span>
      </div>
      <div class="mt-4">
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-bold" id="el-value-${e.id}">—</span>
          <span class="text-xs text-slate-400">μm/m</span>
        </div>
        <div class="mt-2 bg-slate-200 dark:bg-slate-600 rounded-full h-1.5 overflow-hidden">
          <div class="h-1.5 rounded-full transition-all duration-500"
               id="el-bar-${e.id}"
               style="width:0%;background:#10b981"></div>
        </div>
        <div class="flex justify-between text-[10px] mt-1 text-slate-400">
          <span>0</span>
          <span class="text-amber-500">400 ⚠</span>
          <span class="text-red-500">500 μm/m</span>
        </div>
      </div>
    </div>`).join('');
}

// ── Live snapshot ─────────────────────────────────────────────
async function refreshLatest() {
  try {
    const d = await fetchJSON('/api/v2/latest');
    setConnection(true);
    updateHealth(d.health, d.active_alerts);
    updateTimestamp(d.timestamp);
    latestElements = d.elements || [];
    latestElements.forEach(updateElementCard);
    updateStrainDist(latestElements);
    Object.entries(d.environment || {}).forEach(([k, v]) => updateEnvCard(k, v));
  } catch (err) {
    setConnection(false);
    console.error('latest failed:', err);
  }
}

function updateHealth(health, activeAlerts) {
  const count = activeAlerts ?? 0;
  document.getElementById('active-alerts-count').textContent = count;

  // Sidebar badge
  const badge = document.getElementById('nav-alert-badge');
  if (badge) { badge.textContent = count; badge.classList.toggle('hidden', count === 0); }

  if (!health) return;
  const status = labelToStatus(health.label);
  currentScore = health.score;
  currentLabel = health.label;

  document.getElementById('health-label').textContent = health.label;
  document.getElementById('health-sub').textContent =
    status === 'ok'       ? 'All monitored signals within safe range'
    : status === 'warning'  ? 'One or more signals approaching limits'
    : 'One or more signals beyond critical limits';

  setAccent(document.getElementById('health-card'), status);
  updateGauge(health.score, health.label);
}

function updateElementCard(e) {
  const v = document.getElementById(`el-value-${e.id}`);
  if (v) v.textContent = e.microstrain == null ? '—' : Number(e.microstrain).toFixed(0);
  setPill(document.getElementById(`el-status-${e.id}`), e.status);
  setAccent(document.getElementById(`el-card-${e.id}`), e.status);

  const bar = document.getElementById(`el-bar-${e.id}`);
  if (bar && e.microstrain != null) {
    const critHigh = (THRESHOLDS.strain || {}).crit_high ?? 500;
    const pct = Math.min(100, (e.microstrain / critHigh) * 100);
    bar.style.width     = `${pct}%`;
    bar.style.background = statusColor(e.status);
  }
}

function updateEnvCard(key, data) {
  const v = document.getElementById(`env-value-${key}`);
  if (v) v.textContent = data.value == null ? '—' : Number(data.value).toFixed(1);
  setPill(document.getElementById(`env-status-${key}`), data.status);
  setAccent(document.getElementById(`env-card-${key}`), data.status);
}

// ── Alerts ────────────────────────────────────────────────────
async function refreshAlerts() {
  try {
    const active = alertsMode === 'active';
    const alerts = await fetchJSON(`/api/v2/alerts?active=${active}&limit=50`);
    const list   = document.getElementById('alerts-list');
    if (!alerts.length) {
      list.innerHTML = `
        <div class="flex items-center gap-2 text-sm text-emerald-700
                    bg-emerald-50 dark:bg-emerald-950 dark:text-emerald-300
                    border border-emerald-200 dark:border-emerald-800 rounded-lg p-3">
          <span class="dot d-ok"></span>
          No ${active ? 'active ' : ''}alerts — all clear.
        </div>`;
      return;
    }
    list.innerHTML = alerts.map(alertRow).join('');
  } catch (err) {
    console.error('alerts failed:', err);
  }
}

function alertRow(a) {
  const when     = new Date(a.last_seen || a.timestamp).toLocaleString();
  const scope    = a.element ?? 'Device';
  const resolved = a.resolved
    ? `<span class="text-xs text-slate-400">resolved</span>`
    : `<button class="text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
               onclick="resolveAlert(${a.id})">Resolve ✕</button>`;
  return `
    <div class="flex items-center justify-between gap-3
                border border-slate-200 dark:border-slate-700
                rounded-2xl p-3 accent-${a.severity}">
      <div class="flex items-center gap-3 min-w-0">
        <span class="pill st-${a.severity}">${a.severity.toUpperCase()}</span>
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

// ── AI Analysis ───────────────────────────────────────────────
async function refreshAnalysis() {
  try {
    const d      = await fetchJSON('/api/v2/analysis');
    const list   = document.getElementById('analysis-list');
    const causes = d.diagnosis || [];
    if (!causes.length) {
      list.innerHTML = `
        <div class="text-sm text-emerald-700 dark:text-emerald-300
                    bg-emerald-50 dark:bg-emerald-950
                    border border-emerald-200 dark:border-emerald-800
                    rounded-lg p-3 flex items-center gap-2">
          <span class="dot d-ok"></span>
          No developing issues detected from current trends.
        </div>`;
      return;
    }
    list.innerHTML = causes.map(causeCard).join('');
  } catch (err) {
    console.error('analysis failed:', err);
  }
}

function causeCard(f) {
  const sev  = f.likelihood === 'High' ? 'critical' : f.likelihood === 'Moderate' ? 'warning' : 'low';
  const evid = f.evidence.map(e => `<li>${e}</li>`).join('');
  return `
    <div class="bg-slate-50 dark:bg-slate-700/50 rounded-2xl
                border border-slate-200 dark:border-slate-600
                p-4 accent-${sev}">
      <div class="flex items-center justify-between gap-2">
        <p class="font-semibold">${f.cause}</p>
        <span class="pill st-${sev}">${f.likelihood} · ${Math.round(f.score * 100)}%</span>
      </div>
      <ul class="text-sm text-slate-600 dark:text-slate-300 mt-2 space-y-1 list-disc ml-5">${evid}</ul>
      <p class="text-xs text-slate-400 mt-2">Affected: ${(f.affected || []).join(', ')}</p>
      <p class="text-sm text-slate-700 dark:text-slate-300 mt-2">→ ${f.recommendation}</p>
    </div>`;
}

// ── Weather ───────────────────────────────────────────────────
async function refreshWeather() {
  try {
    const d   = await fetchJSON('/api/v2/weather');
    const cur = d.current;
    if (!cur) throw new Error('no current block');

    const code  = cur.weather_code;
    const feels = cur.apparent_temperature;

    document.getElementById('wx-temp').textContent    = cur.temperature_2m?.toFixed(1) ?? '—';
    document.getElementById('wx-desc').textContent    = WMO_DESC[code] ?? 'Unknown';
    document.getElementById('wx-icon').textContent    = WMO_ICON[code] ?? '🌡️';
    document.getElementById('wx-feels').textContent   = `Feels like ${feels?.toFixed(0) ?? '—'}°C`;
    document.getElementById('wx-humidity').textContent = `${cur.relative_humidity_2m ?? '—'}%`;
    document.getElementById('wx-wind').textContent    =
      `${cur.wind_speed_10m?.toFixed(0) ?? '—'} km/h ${windDir(cur.wind_direction_10m)}`;
    document.getElementById('wx-precip').textContent  = `${cur.precipitation ?? 0} mm`;

    document.getElementById('weather-skeleton').classList.add('hidden');
    document.getElementById('weather-content').classList.remove('hidden');
    document.getElementById('weather-error').classList.add('hidden');
  } catch (err) {
    console.error('weather failed:', err);
    document.getElementById('weather-skeleton').classList.add('hidden');
    document.getElementById('weather-error').classList.remove('hidden');
  }
}

function windDir(deg) {
  if (deg == null) return '';
  const dirs = ['N','NE','E','SE','S','SW','W','NW'];
  return dirs[Math.round(deg / 45) % 8];
}

// ── Chart.js trend charts ─────────────────────────────────────
function chartTextColor()  { return isDark() ? '#64748b' : '#94a3b8'; }
function chartGridColor()  { return isDark() ? '#334155' : '#f1f5f9'; }

function initCharts() {
  const txt  = chartTextColor();
  const grid = chartGridColor();

  const base = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 }, color: txt } } },
    scales: {
      x: {
        ticks: { color: txt, maxTicksLimit: 8, font: { size: 10 } },
        grid: { display: false },
      },
      y: {
        ticks: { color: txt, font: { size: 10 } },
        grid: { color: grid },
      },
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
      plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 }, color: txt } } },
      scales: {
        x: base.scales.x,
        y:  { type: 'linear', position: 'left',
              ticks: { color: '#ea580c', font: { size: 10 } },
              grid: { color: grid } },
        y1: { type: 'linear', position: 'right',
              ticks: { color: '#0d9488', font: { size: 10 } },
              grid: { display: false } },
      },
    },
  });
}

function updateChartsForDark() {
  if (!strainChart) return;
  const txt  = chartTextColor();
  const grid = chartGridColor();

  const applyScale = (chart, scaleId, tc, gc) => {
    if (!chart.options.scales[scaleId]) return;
    chart.options.scales[scaleId].ticks.color = tc ?? txt;
    if (gc !== false) chart.options.scales[scaleId].grid.color = gc ?? grid;
  };

  applyScale(strainChart, 'x', null, false);
  applyScale(strainChart, 'y', null, null);
  strainChart.options.plugins.legend.labels.color = txt;
  strainChart.update('none');

  applyScale(envChart, 'x', null, false);
  applyScale(envChart, 'y',  '#ea580c', null);
  applyScale(envChart, 'y1', '#0d9488', false);
  envChart.options.plugins.legend.labels.color = txt;
  envChart.update('none');
}

async function loadHistory(hours) {
  try {
    const d      = await fetchJSON(`/api/v2/history?hours=${hours}&max_points=120`);
    const labels = (d.timestamps || []).map(fmtTime);
    const spec   = THRESHOLDS.strain || {};

    // Strain chart
    const datasets = (d.strains || []).map((s, i) => ({
      label: s.name, data: s.values,
      borderColor: LINE_COLORS[i % LINE_COLORS.length],
      backgroundColor: 'transparent',
      borderWidth: 2, pointRadius: 0, tension: 0.3, spanGaps: true,
    }));
    datasets.push(...thresholdLines(spec, labels.length));
    strainChart.data.labels   = labels;
    strainChart.data.datasets = datasets;
    strainChart.update('none');

    // Env chart
    envChart.data.labels   = labels;
    envChart.data.datasets = [
      { label: 'Temp (°C)',    data: d.series.temperature,
        borderColor: '#ea580c', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y',  spanGaps: true },
      { label: 'Humidity (%)', data: d.series.humidity,
        borderColor: '#0d9488', backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y1', spanGaps: true },
    ];
    envChart.update('none');
  } catch (err) {
    console.error('history failed:', err);
  }
}

function thresholdLines(spec, n) {
  const mk = (val, color, label) => ({
    label, data: Array(n).fill(val),
    borderColor: color, borderWidth: 1.5,
    borderDash: [6, 4], pointRadius: 0,
    fill: false, tension: 0,
  });
  const out = [];
  if (spec.warn_high != null) out.push(mk(spec.warn_high, '#f59e0b', 'Warning'));
  if (spec.crit_high != null) out.push(mk(spec.crit_high, '#ef4444', 'Critical'));
  return out;
}

// ── Controls ──────────────────────────────────────────────────
function wireControls() {
  const on  = 'range-active px-3 py-1 text-xs rounded-md border border-slate-900 bg-slate-900 text-white';
  const off = 'range-btn px-3 py-1 text-xs rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 dark:text-slate-300';

  document.querySelectorAll('.range-btn, .range-active').forEach(btn => {
    btn.addEventListener('click', () => {
      currentHours = Number(btn.dataset.hours);
      document.querySelectorAll('[data-hours]').forEach(b => {
        b.className = b === btn ? on : off;
      });
      loadHistory(currentHours);
    });
  });

  const aActive = document.getElementById('alerts-active-btn');
  const aAll    = document.getElementById('alerts-all-btn');
  const btnOn   = 'px-3 py-1 text-xs rounded-md border border-slate-900 bg-slate-900 text-white';
  const btnOff  = 'px-3 py-1 text-xs rounded-md border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 dark:text-slate-300';

  aActive.addEventListener('click', () => {
    alertsMode = 'active';
    aActive.className = btnOn; aAll.className = btnOff;
    refreshAlerts();
  });
  aAll.addEventListener('click', () => {
    alertsMode = 'all';
    aAll.className = btnOn; aActive.className = btnOff;
    refreshAlerts();
  });
}

// ── Helpers ───────────────────────────────────────────────────
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

function labelToStatus(label) {
  return label === 'Critical' ? 'critical' : label === 'Warning' ? 'warning' : 'ok';
}

function statusColor(s) {
  return s === 'critical' ? '#ef4444' : s === 'warning' ? '#f59e0b' : '#10b981';
}

function setPill(el, status) {
  if (!el) return;
  el.className = `pill st-${status}`;
  el.textContent = (status || 'ok').toUpperCase();
}

function setAccent(el, status) {
  if (!el) return;
  el.classList.remove('accent-ok', 'accent-warning', 'accent-critical', 'accent-low');
  el.classList.add(`accent-${status}`);
}

function setConnection(ok) {
  const dots = [document.getElementById('live-dot'), document.getElementById('sidebar-live-dot')];
  const txts = [document.getElementById('conn-status'), document.getElementById('sidebar-conn')];
  dots.forEach(d => { if (d) d.className = ok ? 'dot d-ok live' : 'dot d-critical'; });
  txts.forEach(t => { if (t) t.textContent = ok ? 'Live' : 'Offline'; });
}

function updateTimestamp(iso) {
  const s = iso ? new Date(iso).toLocaleTimeString() : '—';
  const els = [document.getElementById('last-update'), document.getElementById('sidebar-last-update')];
  els.forEach(el => { if (el) el.textContent = s; });
}

function fmtTime(iso) {
  const d = new Date(iso);
  return currentHours > 48
    ? d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
