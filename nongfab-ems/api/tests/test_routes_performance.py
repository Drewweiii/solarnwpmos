from datetime import datetime, timezone

import nongfab_simulation.dev_data as dev_data
import pytest
from fastapi.testclient import TestClient

import nongfab_api.routes_performance as routes_performance


class _FixedDatetime(datetime):
    """Pins `datetime.now()` to a fixed UTC instant, mid-morning within this
    synthetic model's Thai-daylight window (peaks at 05:00 UTC = 12:00 ICT,
    positive hours 0-10 UTC - see synthetic_day_irradiance_temp()'s own
    docstring) but early enough that "so far" (hours 0-3) is strictly less
    than the full day's eventual total (hours 0-10), so the cumulative-vs-
    full-day assertion below is unambiguous either way. `hours_so_far`/
    `live_efficiency_factor()` are both real-wall-clock-dependent since the
    2026-07-16 "why are the numbers frozen" fix (see routes_performance.py's
    own docstring), so a test asserting on their values needs a fixed `now`
    or it's flaky depending what UTC hour it happens to run at - the exact
    same class of bug already caught once this session in ingestion/nwp's
    backfill tests. Both `routes_performance` (its own `datetime.now()` for
    `hours_so_far`/`live_efficiency_factor`) and `dev_data` (`synthetic_day_
    irradiance_temp()`'s own `datetime.now()` for the day's date) must be
    patched to the same instant, same reasoning as test_ws_live.py's
    identical two-module patch.
    """

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 14, 3, 0, 0, tzinfo=timezone.utc)


def test_get_performance_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/performance/GIS")
    assert resp.status_code == 401


def test_get_performance_returns_metrics_for_viewer(app, token_factory, monkeypatch):
    monkeypatch.setattr(routes_performance, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == "GIS"
    assert body["simulated_zone"] is False
    # Fixed at 03:00 UTC, within this synthetic model's "daylight" window
    # (see _FixedDatetime's own docstring), so cumulative-to-now energy is
    # unambiguously non-zero.
    assert body["ac_energy_kwh_today"] > 0
    assert 0 < body["performance_ratio"] <= 1.0
    assert body["specific_yield_kwh_per_kwp_today"] > 0
    assert "soiling_pct" in body["loss_breakdown"]
    assert len(body["hourly"]) == 24
    assert {"timestamp", "ac_kw", "ssrd_w_m2", "temp_c"} <= body["hourly"][0].keys()
    # ac_energy_kwh_today is now a cumulative-to-now sum (hours 0..3
    # inclusive), not the whole day's total - it must be less than the full
    # day's hourly sum, not equal to it (that was the pre-fix bug).
    assert body["ac_energy_kwh_today"] < sum(p["ac_kw"] for p in body["hourly"])
    assert body["ac_energy_kwh_today"] == pytest.approx(sum(p["ac_kw"] for p in body["hourly"][:4]))


def test_get_performance_includes_zone_coordinates_and_cloud_factor(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/GIS", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["latitude"] == pytest.approx(12.68336875)
    assert body["longitude"] == pytest.approx(101.11986459)
    assert 0.0 <= body["cloud_factor"] <= 1.0


def test_get_performance_jetty_reports_simulated_zone_true(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/Jetty", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["simulated_zone"] is True


def test_get_performance_unknown_zone_returns_404(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/performance/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
