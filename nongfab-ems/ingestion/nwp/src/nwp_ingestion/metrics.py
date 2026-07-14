from prometheus_client import Counter, Gauge, Histogram

FETCH_SUCCESS_TOTAL = Counter("nwp_fetch_success_total", "Successful forecast-hour fetches", ["source"])
FETCH_FAILURE_TOTAL = Counter("nwp_fetch_failure_total", "Failed forecast-hour fetches", ["source", "reason"])
FETCH_DURATION_SECONDS = Histogram("nwp_fetch_duration_seconds", "Time spent on one ingestion cycle (all forecast hours)", ["source"])
CYCLE_FORECAST_HOURS_TOTAL = Gauge("nwp_cycle_forecast_hours_total", "Number of forecast hours ingested in the most recent cycle")

LAST_SSRD_W_M2 = Gauge("nwp_last_ssrd_w_m2", "Most recent SSRD (surface downward shortwave radiation) at f000/f001")
LAST_TEMP2M_C = Gauge("nwp_last_temp2m_c", "Most recent 2m air temperature")
