from prometheus_client import Counter, Gauge, Histogram

FETCH_SUCCESS_TOTAL = Counter("himawari_fetch_success_total", "Successful ingestion cycles", ["source"])
FETCH_FAILURE_TOTAL = Counter("himawari_fetch_failure_total", "Failed ingestion cycles", ["source", "reason"])
FETCH_DURATION_SECONDS = Histogram("himawari_fetch_duration_seconds", "Time spent on one ingestion cycle", ["source"])

LAST_CLOUD_OPACITY_PCT = Gauge("himawari_last_cloud_opacity_pct", "Most recent cloud opacity percentage")
LAST_CLOUD_INDEX = Gauge("himawari_last_cloud_index", "Most recent cloud index")
