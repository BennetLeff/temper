// Dashboard application logic — fetch JSONL, render per-module charts

const JSONL_URL = './pipeline_metrics.jsonl';

let allRecords = [];
let currentModule = 'pipeline';
let charts = [];

function destroyCharts() {
  charts.forEach(c => c.destroy());
  charts = [];
  document.getElementById('dashboard').innerHTML = '';
}

function parseDate(ts) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getFilteredRecords(module, days) {
  const now = Date.now();
  const cutoff = days > 0 ? now - days * 86400000 : 0;

  return allRecords
    .filter(r => r.module === module)
    .filter(r => {
      if (days <= 0) return true;
      const ts = new Date(r.timestamp).getTime();
      return ts >= cutoff;
    })
    .sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
}

function renderPipeline(records) {
  const main = document.getElementById('dashboard');
  const div = document.createElement('div');
  div.className = 'chart-container';
  div.innerHTML = '<h3>Pipeline Wall-Clock Time</h3><canvas id="chart-pipeline-time"></canvas>';
  main.appendChild(div);

  const labels = records.map(r => parseDate(r.timestamp));
  const wallMs = records.map(r => r.metrics?.wall_time_ms || 0);

  const chart = createChart('chart-pipeline-time', 'line', labels, [{
    label: 'Wall Time (ms)',
    data: wallMs,
    borderColor: '#58a6ff',
    backgroundColor: 'rgba(88, 166, 255, 0.1)',
    fill: true,
    tension: 0.2,
  }]);

  if (chart) charts.push(chart);

  const div2 = document.createElement('div');
  div2.className = 'chart-container';
  div2.innerHTML = '<h3>Pipeline Completion Rate</h3><canvas id="chart-pipeline-completion"></canvas>';
  main.appendChild(div2);

  const completion = records.map(r => r.metrics?.completion_pct || 0);
  const chart2 = createChart('chart-pipeline-completion', 'line', labels, [{
    label: 'Completion %',
    data: completion,
    borderColor: '#3fb950',
    backgroundColor: 'rgba(63, 185, 80, 0.1)',
    fill: true,
    tension: 0.2,
  }], {
    scales: {
      x: { ticks: { color: '#8b949e', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: '#21262d' } },
      y: { ticks: { color: '#8b949e', font: { size: 10 } }, grid: { color: '#21262d' }, min: 0, max: 100 },
    },
  });

  if (chart2) charts.push(chart2);
}

function renderLossFn(records) {
  const main = document.getElementById('dashboard');
  const div = document.createElement('div');
  div.className = 'chart-container';
  div.innerHTML = '<h3>Loss Function Timing</h3><canvas id="chart-loss-fn"></canvas>';
  main.appendChild(div);

  const labels = records.map(r => parseDate(r.timestamp));
  const metricKeys = ['overlap_ms', 'spread_ms', 'wirelength_ms', 'boundary_ms'];
  const colors = ['#58a6ff', '#3fb950', '#d2a8ff', '#f0883e'];

  const datasets = metricKeys.map((key, i) => ({
    label: key.replace('_ms', ''),
    data: records.map(r => r.metrics?.[key] || 0),
    backgroundColor: colors[i],
    borderColor: colors[i],
    borderWidth: 0,
  }));

  const chart = createChart('chart-loss-fn', 'bar', labels, datasets, {
    scales: {
      x: { stacked: true, ticks: { color: '#8b949e', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: '#21262d' } },
      y: { stacked: true, ticks: { color: '#8b949e', font: { size: 10 } }, grid: { color: '#21262d' }, title: { display: true, text: 'ms', color: '#8b949e' } },
    },
  });

  if (chart) charts.push(chart);
}

function renderRouterBench(records) {
  const main = document.getElementById('dashboard');
  const byBoard = {};
  records.forEach(r => {
    const board = r.board || 'unknown';
    if (!byBoard[board]) byBoard[board] = [];
    byBoard[board].push(r);
  });

  Object.entries(byBoard).forEach(([board, recs]) => {
    const div = document.createElement('div');
    div.className = 'chart-container';
    const canvasId = 'chart-router-' + board.replace(/[^a-zA-Z0-9]/g, '-');
    div.innerHTML = `<h3>${board} — p95 Latency</h3><canvas id="${canvasId}"></canvas>`;
    main.appendChild(div);

    const labels = recs.map(r => parseDate(r.timestamp));
    const p95Data = recs.map(r => r.metrics?.p95_latency_ms || 0);

    const chart = createChart(canvasId, 'line', labels, [{
      label: 'p95 Latency (ms)',
      data: p95Data,
      borderColor: '#f0883e',
      backgroundColor: 'rgba(240, 136, 62, 0.1)',
      fill: true,
      tension: 0.2,
    }]);

    if (chart) charts.push(chart);
  });
}

function renderModule() {
  destroyCharts();
  const days = parseInt(document.getElementById('time-window').value, 10);
  const records = getFilteredRecords(currentModule, days);

  if (records.length === 0) {
    document.getElementById('no-data').style.display = 'block';
    return;
  }
  document.getElementById('no-data').style.display = 'none';

  switch (currentModule) {
    case 'pipeline':
      renderPipeline(records);
      break;
    case 'loss-fn':
      renderLossFn(records);
      break;
    case 'router-bench':
      renderRouterBench(records);
      break;
  }
}

function switchModule(module) {
  currentModule = module;
  document.querySelectorAll('#module-nav button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.module === module);
  });
  renderModule();
}

function updateLastUpdated() {
  if (allRecords.length === 0) return;
  const latest = allRecords.reduce((a, b) =>
    (a.timestamp || '') > (b.timestamp || '') ? a : b
  );
  document.getElementById('last-updated').textContent =
    'Last updated: ' + new Date(latest.timestamp).toLocaleString();
}

async function loadData() {
  try {
    const response = await fetch(JSONL_URL);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const text = await response.text();
    allRecords = text.trim().split('\n').filter(Boolean).map(line => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
    document.getElementById('loading').style.display = 'none';

    if (allRecords.length === 0) {
      document.getElementById('no-data').style.display = 'block';
    } else {
      updateLastUpdated();
      renderModule();
    }
  } catch (err) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('error').style.display = 'block';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadData();

  document.querySelectorAll('#module-nav button').forEach(btn => {
    btn.addEventListener('click', () => switchModule(btn.dataset.module));
  });

  document.getElementById('time-window').addEventListener('change', renderModule);
});
