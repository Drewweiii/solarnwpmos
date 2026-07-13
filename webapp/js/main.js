import { fetchForecast } from './weather.js';
import { forecastToPower, DEFAULT_LOSSES } from './pvModel.js';
import { computeEnergyReport } from './energyReport.js';
import { runBacktest } from './backtest.js';

const $ = (id) => document.getElementById(id);

const LOSS_COLORS = {
  temperature: 'var(--series-1)',
  shading: 'var(--series-2)',
  soiling: 'var(--series-3)',
  inverter: 'var(--series-4)',
  mismatch: 'var(--series-5)',
  dcWiring: 'var(--series-6)',
};
const LOSS_LABELS = {
  temperature: 'Temperature',
  shading: 'Shading',
  soiling: 'Soiling',
  inverter: 'Inverter',
  mismatch: 'Mismatch',
  dcWiring: 'DC Wiring',
};

function bindRangeReadout(rangeId, readoutId, formatter) {
  const el = $(rangeId);
  const readout = $(readoutId);
  const update = () => (readout.textContent = formatter(Number(el.value)));
  el.addEventListener('input', update);
  update();
}

bindRangeReadout('capacity', 'capacity-val', (v) => `${v} kWp`);
bindRangeReadout('wattage', 'wattage-val', (v) => `${v} W`);
bindRangeReadout('tilt', 'tilt-val', (v) => `${v}°`);
bindRangeReadout('azimuth', 'azimuth-val', (v) => `${v}°`);
bindRangeReadout('shading', 'shading-val', (v) => `${v}%`);
bindRangeReadout('soiling', 'soiling-val', (v) => `${v}%`);
bindRangeReadout('inverter', 'inverter-val', (v) => `${v}%`);
bindRangeReadout('mismatch', 'mismatch-val', (v) => `${v}%`);
bindRangeReadout('dcwiring', 'dcwiring-val', (v) => `${v}%`);
bindRangeReadout('backtest-days', 'backtest-days-val', (v) => `${v} days`);
bindRangeReadout('bias', 'bias-val', (v) => `${v}%`);
bindRangeReadout('noise', 'noise-val', (v) => `${v}%`);

$('use-location').addEventListener('click', () => {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition((pos) => {
    $('lat').value = pos.coords.latitude.toFixed(4);
    $('lon').value = pos.coords.longitude.toFixed(4);
  });
});

function readSystem() {
  return {
    lat: Number($('lat').value),
    lon: Number($('lon').value),
    capacityKw: Number($('capacity').value),
    tiltDeg: Number($('tilt').value),
    azimuthDeg: Number($('azimuth').value),
    losses: {
      ...DEFAULT_LOSSES,
      shading: Number($('shading').value) / 100,
      soiling: Number($('soiling').value) / 100,
      inverter: Number($('inverter').value) / 100,
      mismatch: Number($('mismatch').value) / 100,
      dcWiring: Number($('dcwiring').value) / 100,
    },
  };
}

let forecastChart = null;
let backtestChart = null;
let backtestSeries = null;

function setStatus(msg, isError = false) {
  const el = $('status');
  el.textContent = msg;
  el.classList.toggle('error', isError);
}

async function renderForecast(system) {
  const samples = await fetchForecast(system.lat, system.lon, 3);
  const points = samples.map((s) => ({
    label: s.time.toLocaleString([], { weekday: 'short', hour: '2-digit' }),
    power: forecastToPower(s, system),
  }));

  const ctx = $('forecast-chart').getContext('2d');
  if (forecastChart) forecastChart.destroy();
  forecastChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: points.map((p) => p.label),
      datasets: [
        {
          label: 'Forecast power (kW)',
          data: points.map((p) => p.power),
          backgroundColor: getCss('--series-1'),
          borderRadius: 4,
          maxBarThickness: 18,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxRotation: 60, minRotation: 60, autoSkip: true, maxTicksLimit: 24 }, grid: { display: false } },
        y: { title: { display: true, text: 'kW' }, grid: { color: getCss('--gridline') } },
      },
    },
  });
}

function getCss(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

async function renderEnergyReport(system) {
  const report = await computeEnergyReport(system);

  $('summary-capacity').innerHTML = `${report.systemSummary.capacityKw}<span class="unit">kWp</span>`;
  $('summary-panels').textContent = report.systemSummary.panelCount;
  $('summary-roof').innerHTML = `${Math.round(report.systemSummary.roofAreaM2)}<span class="unit">m²</span>`;

  $('annual-generation').textContent = `${report.annualGenerationMwh.toFixed(1)} MWh`;
  $('specific-yield').textContent = Math.round(report.specificYieldKwhPerKwp);
  $('performance-ratio').textContent = report.performanceRatioPct.toFixed(1);
  $('total-loss').textContent = `${report.totalSystemLossPct.toFixed(1)}%`;
  $('solar-access').textContent = `${report.solarAccessPct.toFixed(0)}%`;

  const container = $('losses-breakdown');
  container.innerHTML = '';
  for (const [key, pct] of Object.entries(report.lossesBreakdownPct)) {
    const row = document.createElement('div');
    row.className = 'loss-row';
    row.innerHTML = `
      <span>${LOSS_LABELS[key]}</span>
      <span class="loss-bar-track"><span class="loss-bar-fill" style="width:${Math.min(100, pct * 4)}%;background:${LOSS_COLORS[key]}"></span></span>
      <span>${pct.toFixed(1)}%</span>
    `;
    container.appendChild(row);
  }
}

function renderBacktestDay(dayIndex) {
  const rows = backtestSeries[dayIndex];
  const labels = rows.map((r) => r.time.toLocaleTimeString([], { hour: '2-digit' }));

  const ctx = $('backtest-chart').getContext('2d');
  if (backtestChart) backtestChart.destroy();
  backtestChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Actual', data: rows.map((r) => r.actual), borderColor: getCss('--series-1'), backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.25 },
        { label: 'Raw NWP', data: rows.map((r) => r.rawForecast), borderColor: getCss('--series-2'), backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.25 },
        { label: 'Persistence', data: rows.map((r) => r.persistence), borderColor: getCss('--series-3'), backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.25 },
        { label: 'MOS+KF', data: rows.map((r) => r.kfForecast), borderColor: getCss('--series-4'), backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.25 },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom' } },
      scales: {
        x: { grid: { display: false } },
        y: { title: { display: true, text: 'kW' }, grid: { color: getCss('--gridline') } },
      },
    },
  });
  $('day-label').textContent = rows[0].time.toLocaleDateString();
}

function renderMetricsTable(metrics) {
  const tbody = document.querySelector('#metrics-table tbody');
  tbody.innerHTML = '';
  const rowsDef = [
    ['Raw NWP', metrics.rawNwp],
    ['Persistence', metrics.persistence],
    ['MOS+KF', metrics.mosKf],
  ];
  const bestRmse = Math.min(...rowsDef.map(([, m]) => m.rmse));
  for (const [name, m] of rowsDef) {
    const tr = document.createElement('tr');
    const rmseClass = m.rmse === bestRmse ? 'best' : '';
    tr.innerHTML = `<td>${name}</td><td class="${rmseClass}">${m.rmse.toFixed(3)}</td><td>${m.mae.toFixed(3)}</td><td>${m.mape.toFixed(1)}</td><td>${m.mbe.toFixed(3)}</td><td>${m.nrmseCap.toFixed(1)}</td>`;
    tbody.appendChild(tr);
  }
}

async function renderBacktest(system) {
  const { series, metrics } = await runBacktest(system, {
    days: Number($('backtest-days').value),
    forecastBiasStd: Number($('bias').value) / 100,
    forecastNoiseStd: Number($('noise').value) / 100,
  });
  backtestSeries = series;

  const daySelect = $('day-select');
  daySelect.max = series.length - 1;
  daySelect.value = series.length - 1;
  daySelect.oninput = () => renderBacktestDay(Number(daySelect.value));

  renderBacktestDay(series.length - 1);
  renderMetricsTable(metrics);
}

async function runAll() {
  const runBtn = $('run');
  runBtn.disabled = true;
  setStatus('Fetching weather data and running models…');
  try {
    const system = readSystem();
    await Promise.all([renderForecast(system), renderEnergyReport(system), renderBacktest(system)]);
    setStatus('Done.');
  } catch (err) {
    console.error(err);
    setStatus(`Error: ${err.message}`, true);
  } finally {
    runBtn.disabled = false;
  }
}

$('run').addEventListener('click', runAll);
runAll();
