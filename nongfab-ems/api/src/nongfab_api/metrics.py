"""Prometheus metrics for the API's own HTTP traffic. Unlike Module 1/2's
ingestion daemons (which have no web framework of their own, so they run
prometheus_client's start_http_server() on a separate port), the API already
serves HTTP - so these are exposed via a /metrics route on the same FastAPI
app instead (see main.py's prometheus_metrics_middleware and /metrics
route). Matches infra/prometheus/prometheus.yml's existing `nongfab-api`
job, which scrapes a single target on the API's normal port.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "nongfab_api_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

REQUEST_DURATION_SECONDS = Histogram(
    "nongfab_api_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
