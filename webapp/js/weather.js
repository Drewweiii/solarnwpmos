// Open-Meteo client: pulls hourly GHI, ambient temperature and cloud cover
// as a stand-in for the WRF-NWP feed used in the original research (wrf_measurement.mat).

const FORECAST_URL = 'https://api.open-meteo.com/v1/forecast';
const ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive';

export async function fetchForecast(lat, lon, days = 3) {
  const url = new URL(FORECAST_URL);
  url.searchParams.set('latitude', lat);
  url.searchParams.set('longitude', lon);
  url.searchParams.set(
    'hourly',
    'shortwave_radiation,direct_normal_irradiance,diffuse_radiation,temperature_2m,cloud_cover'
  );
  url.searchParams.set('forecast_days', String(days));
  url.searchParams.set('timezone', 'UTC');

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Open-Meteo forecast request failed: ${res.status}`);
  const data = await res.json();

  return data.hourly.time.map((t, i) => ({
    time: new Date(t + 'Z'), // Open-Meteo returns naive local(=UTC here) timestamps with no offset
    ghi: data.hourly.shortwave_radiation[i] ?? 0,
    dni: data.hourly.direct_normal_irradiance[i] ?? 0,
    dhi: data.hourly.diffuse_radiation[i] ?? 0,
    temp: data.hourly.temperature_2m[i] ?? 25,
    cloudCover: data.hourly.cloud_cover[i] ?? 0,
  }));
}

// Hourly reanalysis (actuals) for the trailing `days`, used as ground truth
// for backtesting the forecasting models against a simulated NWP feed.
export async function fetchHistoricalHourly(lat, lon, days = 30) {
  const end = new Date();
  end.setDate(end.getDate() - 2); // archive lags a couple of days behind real time
  const start = new Date(end);
  start.setDate(start.getDate() - days);

  const fmt = (d) => d.toISOString().slice(0, 10);

  const url = new URL(ARCHIVE_URL);
  url.searchParams.set('latitude', lat);
  url.searchParams.set('longitude', lon);
  url.searchParams.set('start_date', fmt(start));
  url.searchParams.set('end_date', fmt(end));
  url.searchParams.set(
    'hourly',
    'shortwave_radiation,direct_normal_irradiance,diffuse_radiation,temperature_2m'
  );
  url.searchParams.set('timezone', 'UTC');

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Open-Meteo archive request failed: ${res.status}`);
  const data = await res.json();

  return data.hourly.time.map((t, i) => ({
    time: new Date(t + 'Z'),
    ghi: data.hourly.shortwave_radiation[i] ?? 0,
    dni: data.hourly.direct_normal_irradiance[i] ?? 0,
    dhi: data.hourly.diffuse_radiation[i] ?? 0,
    temp: data.hourly.temperature_2m[i] ?? 25,
  }));
}
