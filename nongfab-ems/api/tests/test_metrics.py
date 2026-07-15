"""Regression coverage for the /metrics route and the request-counting
middleware behind it - in particular that parameterized routes are recorded
under their route *template* (e.g. "/forecast/{zone}/{horizon}") rather than
the raw per-request path, so distinct zone values don't fragment into
separate metric series, and that unmatched paths collapse to a single
"not_found" label instead of leaking the raw (attacker-controlled) URL into
a label value.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _metric_value(metrics_text: str, line_prefix: str) -> float | None:
    for line in metrics_text.splitlines():
        if line.startswith(line_prefix):
            return float(line.rsplit(" ", 1)[1])
    return None


def test_metrics_endpoint_exposes_prometheus_text_format(app):
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "nongfab_api_requests_total" in resp.text
    assert "nongfab_api_request_duration_seconds" in resp.text


def test_request_counter_increments_by_exact_delta_for_healthz(app):
    prefix = 'nongfab_api_requests_total{method="GET",path="/healthz",status_code="200"}'
    with TestClient(app) as client:
        before = _metric_value(client.get("/metrics").text, prefix) or 0.0
        client.get("/healthz")
        client.get("/healthz")
        after = _metric_value(client.get("/metrics").text, prefix)
    assert after == before + 2


def test_parameterized_route_aggregates_under_its_template_not_raw_path(app, token_factory):
    token = token_factory("viewer")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        client.get("/forecast/Nowhere/hour", headers=headers)
        client.get("/forecast/GIS/century", headers=headers)
        text = client.get("/metrics").text
    assert 'path="/forecast/Nowhere/hour"' not in text
    assert 'path="/forecast/GIS/century"' not in text
    assert 'nongfab_api_requests_total{method="GET",path="/forecast/{zone}/{horizon}"' in text


def test_unmatched_path_collapses_to_not_found_label(app):
    with TestClient(app) as client:
        client.get("/this-route-does-not-exist")
        text = client.get("/metrics").text
    assert "/this-route-does-not-exist" not in text
    assert 'nongfab_api_requests_total{method="GET",path="not_found",status_code="404"}' in text


def test_request_duration_histogram_records_healthz(app):
    with TestClient(app) as client:
        client.get("/healthz")
        text = client.get("/metrics").text
    assert 'nongfab_api_request_duration_seconds_count{method="GET",path="/healthz"}' in text
