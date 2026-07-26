"""GET /forecast/{zone}/verification (2026-07-25) - auth, honest-empty when the
two histories don't overlap, and a real scored window."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nongfab_forecast.serving import GENERATED_POWER_HORIZON

from nongfab_api.config import Settings
from nongfab_api.main import create_app


class _Point:
    """Matches what record_forecast_points reads off each item."""

    def __init__(self, timestamp: datetime, pred: float):
        self.timestamp = timestamp
        self.pred = pred
        self.lower = None
        self.upper = None
        self.algorithm = None
        self.error = None


class _Nwp:
    """Matches what insert_nwp_points reads off each point."""

    def __init__(self, valid_time: datetime, issue_time: datetime, ssrd_w_m2: float):
        self.valid_time = valid_time
        self.issue_time = issue_time
        self.ssrd_w_m2 = ssrd_w_m2
        self.temp2m_c = 30.0
        self.wind10m_u_ms = 0.0
        self.wind10m_v_ms = 0.0
        self.relative_humidity_pct = 70.0
        self.precip_mm = 0.0
        self.source = "test"


def _file_backed_app(engine, tmp_path):
    settings = Settings(
        jwt_secret_key="test-secret",
        seed_demo_users=True,
        enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    return create_app(settings=settings, engine=engine), settings


def test_verification_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/forecast/GIS/verification").status_code == 401


def test_verification_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/Nowhere/verification", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_verification_rejects_an_out_of_range_window(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/verification?days=500", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_verification_is_unavailable_with_a_reason_when_there_is_no_history(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/forecast/GIS/verification", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["daylight"] is None
    assert body["by_lead"] == []
    # The capacity is registry data, so it's known even with no history.
    assert body["ac_capacity_kw"] > 0


def test_verification_scores_the_window_once_forecasts_and_actuals_overlap(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        # 12 hours of forecasts, each issued 2h ahead of its target. The actual
        # RISES 1 kW/hour, so persistence ("it'll be what it is now") is wrong by
        # 2 kW at a 2h lead while the forecast is only ever 1 kW high - a model
        # that genuinely beats persistence, i.e. skill = 1 - 1/2 = 0.5. A flat
        # actual would make persistence perfect and leave the skill undefined.
        for h in range(1, 13):
            target = now - timedelta(hours=h)
            actual_kw = 20.0 + h
            store.record_forecast_points("GIS", "hour", target - timedelta(hours=2), [_Point(target, actual_kw + 1)])
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, actual_kw)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["horizon"] == "hour"
    assert body["window_days"] == 7
    assert body["daylight"]["n"] == 12
    assert body["daylight"]["mae_kw"] > 0
    assert body["daylight"]["mbe_kw"] > 0  # forecasts ran high
    assert body["daylight"]["nrmse_pct"] > 0
    # Persistence had a real reference here (the actual 2h before each target),
    # and the model beats it 1 kW to 2 kW -> skill 0.5.
    assert body["daylight"]["persistence_rmse_kw"] == pytest.approx(2.0)
    assert body["daylight"]["skill_score"] == pytest.approx(0.5)
    # Every lead bucket is present, and the 1-3h one holds these pairs.
    labels = [row["lead_bucket"] for row in body["by_lead"]]
    assert labels == ["0-1h", "1-3h", "3-6h", "6-24h", "24h+"]
    by_label = {row["lead_bucket"]: row["metrics"] for row in body["by_lead"]}
    assert by_label["1-3h"]["n"] == 12
    assert by_label["24h+"]["n"] == 0
    assert body["lead_time_note"]


def test_verification_reports_no_overlap_distinctly_from_no_data(engine, tmp_path):
    """Both stores have rows, but for different hours - the reason must say so
    rather than reporting a zero-error window."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        forecast_hour = now - timedelta(hours=2)
        actual_hour = now - timedelta(hours=50)
        store.record_forecast_points("GIS", "hour", forecast_hour - timedelta(hours=1), [_Point(forecast_hour, 30.0)])
        store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, actual_hour, [_Point(actual_hour, 28.0)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is False
    assert "ทับกัน" in body["reason"]


class _BandPoint(_Point):
    """A forecast point that also carries the published interval."""

    def __init__(self, timestamp: datetime, pred: float, lower: float, upper: float):
        super().__init__(timestamp, pred)
        self.lower = lower
        self.upper = upper


def test_verification_scores_the_published_interval_not_just_the_point(engine, tmp_path):
    """Project A (2026-07-25): the shaded band on the chart is a nominal 90%
    interval and nothing ever checked whether it held. Here 3 of 12 outcomes are
    deliberately pushed outside a +/-2 kW band, so the route must report 75%
    coverage against a 90% nominal - i.e. overconfident - rather than staying
    silent about the band."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for h in range(1, 13):
            target = now - timedelta(hours=h)
            actual_kw = 20.0 + h
            # The band is centred on the actual, so it contains it - except for
            # the three hours where the forecast is thrown far enough off that
            # the actual falls outside.
            predicted = actual_kw + (10.0 if h <= 3 else 0.5)
            store.record_forecast_points(
                "GIS",
                "hour",
                target - timedelta(hours=2),
                [_BandPoint(target, predicted, predicted - 2.0, predicted + 2.0)],
            )
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, actual_kw)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    interval = body["interval"]
    assert interval["n"] == 12
    assert interval["nominal_pct"] == pytest.approx(90.0)
    assert interval["coverage_pct"] == pytest.approx(75.0)
    assert interval["coverage_gap_pct"] == pytest.approx(-15.0)
    # The three misses are all on one side (forecast far too high), which is a
    # mis-centred band rather than merely a narrow one.
    assert interval["miss_low_pct"] == pytest.approx(25.0)
    assert interval["miss_high_pct"] == pytest.approx(0.0)
    assert interval["mean_width_kw"] == pytest.approx(4.0)
    assert interval["pinaw_pct"] == pytest.approx(8.0)  # 4 kW on GIS's 50 kW AC
    assert interval["pinball_kw"] > 0
    assert body["interval_note"] and body["pinball_note"]

    by_label = {row["lead_bucket"]: row["interval"] for row in body["interval_by_lead"]}
    assert by_label["1-3h"]["n"] == 12
    assert by_label["24h+"]["n"] == 0


def test_verification_says_no_band_was_published_rather_than_zero_coverage(engine, tmp_path):
    """The physics-baseline fallback publishes no interval. That must read as
    "nothing to check", never as "the band covered 0% of outcomes"."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for h in range(1, 5):
            target = now - timedelta(hours=h)
            store.record_forecast_points("GIS", "hour", target - timedelta(hours=1), [_Point(target, 20.0 + h)])
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, 20.0 + h)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    assert body["daylight"]["n"] == 4  # the point forecast still scores fine
    assert body["interval"]["n"] == 0


def test_verification_splits_accuracy_by_sky_condition(engine, tmp_path):
    """Project C (2026-07-25): one site-wide RMSE averages an easy cloudless
    morning together with a convective afternoon. Here the model is perfect on
    the bright hours and badly wrong on the dark ones, so the split must show
    that while the headline figure hides it."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    # Anchor on a bright midday hour (05:00Z = 12:00 ICT) so the clear-sky
    # reference is large and kt is well defined for every hour used.
    now = datetime.now(timezone.utc).replace(hour=5, minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for h in range(1, 5):
            target = now - timedelta(days=h)
            bright = h <= 2
            actual_kw = 40.0 if bright else 8.0
            predicted = actual_kw if bright else actual_kw + 25.0
            store.record_forecast_points("GIS", "hour", target - timedelta(hours=1), [_Point(target, predicted)])
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, actual_kw)])
            # The NWP row that decides the sky label for that hour: a bright
            # 900 W/m2 midday reads as clear, 80 W/m2 at the same hour as overcast.
            store.insert_nwp_points([_Nwp(target, target - timedelta(hours=1), 900.0 if bright else 80.0)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    labels = [row["sky"] for row in body["by_sky"]]
    assert labels == ["clear", "partly_cloudy", "overcast"]
    by_sky = {row["sky"]: row["metrics"] for row in body["by_sky"]}
    # Bright hours: forecast was exact. Dark hours: 25 kW too high.
    assert by_sky["clear"]["n"] == 2
    assert by_sky["clear"]["rmse_kw"] == pytest.approx(0.0)
    assert by_sky["overcast"]["n"] == 2
    assert by_sky["overcast"]["rmse_kw"] == pytest.approx(25.0)
    assert body["sky_note"]


def test_verification_still_serves_metrics_when_the_sky_split_has_no_weather(engine, tmp_path):
    """No NWP history at all: the accuracy figures must still come back, with
    every hour reported as unclassified rather than the route failing."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        store = app.state.real_data_store
        for h in range(1, 4):
            target = now - timedelta(hours=h)
            store.record_forecast_points("GIS", "hour", target - timedelta(hours=1), [_Point(target, 30.0)])
            store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, target, [_Point(target, 28.0)])

        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/forecast/GIS/verification?days=7", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    assert body["daylight"]["n"] == 3
    assert body["sky_unclassified_n"] == 3
    assert all(row["metrics"]["n"] == 0 for row in body["by_sky"])
