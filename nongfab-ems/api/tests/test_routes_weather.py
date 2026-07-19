from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import nongfab_simulation.dev_data as dev_data
import pytest
from fastapi.testclient import TestClient

import nongfab_api.routes_weather as routes_weather
from nongfab_api.config import Settings
from nongfab_api.main import create_app

_FIXED_NOW = datetime(2026, 7, 16, 6, 30, 0, tzinfo=timezone.utc)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW


@dataclass
class _FakeNWPPoint:
    valid_time: datetime
    issue_time: datetime
    ssrd_w_m2: float
    temp2m_c: float
    wind10m_u_ms: float
    wind10m_v_ms: float
    relative_humidity_pct: float
    source: str
    precip_mm: float | None = None


def _real_points_around(now: datetime, hours_each_side: int) -> list[_FakeNWPPoint]:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    return [
        _FakeNWPPoint(
            valid_time=hour_start + timedelta(hours=offset),
            issue_time=hour_start,
            ssrd_w_m2=500.0,
            temp2m_c=30.0 + offset * 0.1,
            wind10m_u_ms=1.0,
            wind10m_v_ms=1.0,
            relative_humidity_pct=70.0,
            source="test-real",
        )
        for offset in range(-hours_each_side, hours_each_side + 1)
    ]


def test_get_weather_strip_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/weather/strip")
    assert resp.status_code == 401


def test_get_weather_strip_falls_back_to_synthetic_when_store_empty(app, token_factory, monkeypatch):
    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/weather/strip?hours_each_side=4", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_source"] == "synthetic"
    assert len(body["points"]) == 9  # -4..+4 inclusive
    assert {"timestamp", "temp_c", "ssrd_w_m2"} <= body["points"][0].keys()


def test_get_weather_strip_synthetic_points_carry_astronomy_fields_but_not_rh_or_wind(app, token_factory, monkeypatch):
    """2026-07-18: /weather/strip points gained the rest of the Songsiri
    9-variable set (see get_current_conditions's own docstring) for
    ForecastPage's grouped variable graphs. clearsky/zenith/cos_zenith are
    pure pvlib astronomy, so they're populated even in synthetic-fallback
    mode; RH/wind speed stay None since the synthetic baseline never models
    them."""
    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/weather/strip?hours_each_side=2", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["data_source"] == "synthetic"
    for point in body["points"]:
        assert point["clearsky_ghi_w_m2"] is not None
        assert point["zenith_deg"] is not None
        assert -1.0 <= point["cos_zenith"] <= 1.0
        assert point["relative_humidity_pct"] is None
        assert point["wind_speed_ms"] is None


def _app_with_file_backed_store(engine, tmp_path):
    """A real_data_store backed by a real file, not `:memory:` - `:memory:`
    needs a single held-open connection (see local_store.py's own docstring),
    which is thread-affine and breaks when the test's own thread (populating
    the store) differs from TestClient's request-handling thread. A file path
    reconnects per call instead, sidestepping that entirely - the shared
    `app`/`settings` fixtures default to `:memory:`, so these two tests build
    their own app rather than using them.
    """
    settings = Settings(
        jwt_secret_key="test-secret", seed_demo_users=True, enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    return create_app(settings=settings, engine=engine), settings


def test_get_weather_strip_uses_real_data_once_window_covered(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        # real_data_store is only set on app.state once the lifespan startup
        # has run (see main.py) - inside the TestClient context, not before it.
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=6))
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/strip?hours_each_side=4", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["data_source"] == "real"
    assert len(body["points"]) == 9
    # The center point (offset 0, i.e. the fixed "now"'s own hour) should be
    # the real inserted value (temp2m_c=30.0), not a synthetic one.
    hour_start = _FIXED_NOW.replace(minute=0, second=0, microsecond=0)
    center = next(p for p in body["points"] if datetime.fromisoformat(p["timestamp"]) == hour_start)
    assert center["temp_c"] == pytest.approx(30.0)
    # RH/wind speed - real, straight off the inserted NWP row (u=v=1.0).
    assert center["relative_humidity_pct"] == pytest.approx(70.0)
    assert center["wind_speed_ms"] == pytest.approx(2.0**0.5)
    # I_clr/zenith/cos_zenith/k-hat - computed, always present regardless of
    # real-vs-synthetic data source.
    assert center["clearsky_ghi_w_m2"] is not None


@dataclass
class _FakeCloudFrame:
    observed_at: datetime
    source: str
    nong_fab_cloud_opacity_pct: float
    nong_fab_cloud_index: float
    motion_speed_kmh: float | None = None
    motion_direction_deg: float | None = None


def test_get_cloud_conditions_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/weather/clouds")
    assert resp.status_code == 401


def test_get_cloud_conditions_unavailable_when_store_empty(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/weather/clouds", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["cloud_opacity_pct"] is None


def test_get_cloud_conditions_returns_latest_reading_with_motion(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        app.state.real_data_store.insert_cloud_frames(
            [
                _FakeCloudFrame(
                    observed_at=_FIXED_NOW - timedelta(minutes=10), source="test",
                    nong_fab_cloud_opacity_pct=35.0, nong_fab_cloud_index=0.4,
                ),
                # Latest row (by observed_at) - this is the one that should win.
                _FakeCloudFrame(
                    observed_at=_FIXED_NOW - timedelta(minutes=2), source="test",
                    nong_fab_cloud_opacity_pct=62.0, nong_fab_cloud_index=0.7,
                    motion_speed_kmh=18.5, motion_direction_deg=210.0,
                ),
            ]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/clouds", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["available"] is True
    assert body["cloud_opacity_pct"] == pytest.approx(62.0)
    assert body["motion_speed_kmh"] == pytest.approx(18.5)
    assert body["motion_direction_deg"] == pytest.approx(210.0)


def test_get_cloud_conditions_unavailable_when_latest_reading_too_stale(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        app.state.real_data_store.insert_cloud_frames(
            [
                _FakeCloudFrame(
                    observed_at=_FIXED_NOW - timedelta(hours=2), source="test",
                    nong_fab_cloud_opacity_pct=50.0, nong_fab_cloud_index=0.5,
                )
            ]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/clouds", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["available"] is False


def test_get_precipitation_conditions_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/weather/precipitation")
    assert resp.status_code == 401


def test_get_precipitation_conditions_unavailable_when_store_empty(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/weather/precipitation", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["precip_mm"] is None
    assert body["intensity"] is None


def test_get_precipitation_conditions_unavailable_when_no_row_carries_precip(engine, tmp_path, monkeypatch):
    """Rows exist (e.g. PVGIS backfill, or NWP rows ingested before this feature
    existed) but none has a non-null precip_mm - must not be confused with a
    genuine "it's dry" reading.
    """
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=1))
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/precipitation", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["available"] is False


def test_get_precipitation_conditions_returns_nearest_reading_with_intensity(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    hour_start = _FIXED_NOW.replace(minute=0, second=0, microsecond=0)
    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(
            [
                # Far-future row (outside _PRECIP_MAX_LEAD_HOURS) - must lose to the
                # near-term one below even though it's a heavier rain value.
                _FakeNWPPoint(
                    valid_time=hour_start + timedelta(hours=24), issue_time=hour_start,
                    ssrd_w_m2=500.0, temp2m_c=30.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0,
                    relative_humidity_pct=70.0, source="test-real", precip_mm=20.0,
                ),
                # Near-"now" row - this is the one that should win.
                _FakeNWPPoint(
                    valid_time=hour_start, issue_time=hour_start,
                    ssrd_w_m2=500.0, temp2m_c=30.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0,
                    relative_humidity_pct=70.0, source="test-real", precip_mm=4.0,
                ),
            ]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/precipitation", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert body["available"] is True
    assert body["precip_mm"] == pytest.approx(4.0)
    assert body["intensity"] == "moderate"  # 2.5 <= 4.0 < 7.6


@pytest.mark.parametrize(
    "precip_mm,expected_intensity",
    [(0.0, "none"), (0.05, "none"), (1.0, "light"), (5.0, "moderate"), (10.0, "heavy")],
)
def test_get_precipitation_conditions_intensity_bands(engine, tmp_path, monkeypatch, precip_mm, expected_intensity):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    hour_start = _FIXED_NOW.replace(minute=0, second=0, microsecond=0)
    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(
            [
                _FakeNWPPoint(
                    valid_time=hour_start, issue_time=hour_start,
                    ssrd_w_m2=500.0, temp2m_c=30.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0,
                    relative_humidity_pct=70.0, source="test-real", precip_mm=precip_mm,
                ),
            ]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/precipitation", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["intensity"] == expected_intensity


def test_get_weather_strip_nulls_relative_humidity_and_wind_for_future_hours_only(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)
    hour_start = _FIXED_NOW.replace(minute=0, second=0, microsecond=0)

    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=4))
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/strip?hours_each_side=4", headers={"Authorization": f"Bearer {token}"})
    points = resp.json()["points"]

    past_point = next(p for p in points if datetime.fromisoformat(p["timestamp"]) == hour_start - timedelta(hours=2))
    assert past_point["relative_humidity_pct"] == pytest.approx(70.0)
    assert past_point["wind_speed_ms"] is not None

    future_point = next(p for p in points if datetime.fromisoformat(p["timestamp"]) == hour_start + timedelta(hours=2))
    assert future_point["relative_humidity_pct"] is None
    assert future_point["wind_speed_ms"] is None
    # ssrd/temp, unlike RH/wind, are still shown for the future - they're the
    # already-established I_wrf/T forecast, this isn't a new restriction.
    assert future_point["ssrd_w_m2"] is not None


def test_get_weather_strip_falls_back_to_synthetic_when_real_coverage_too_sparse(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    monkeypatch.setattr(dev_data, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    # Only 2 of the 9 needed hourly slots covered - below the 80% coverage
    # threshold, so this must still fall back to synthetic rather than show a
    # strip full of gaps.
    sparse = _real_points_around(_FIXED_NOW, hours_each_side=0) + [
        _FakeNWPPoint(
            valid_time=_FIXED_NOW.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            issue_time=_FIXED_NOW, ssrd_w_m2=500.0, temp2m_c=31.0,
            wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=70.0, source="test-real",
        )
    ]

    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(sparse)
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/strip?hours_each_side=4", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["data_source"] == "synthetic"


@dataclass
class _FakeUVObservation:
    observation_date: object  # datetime.date
    uv_index: float
    source: str


def test_get_current_conditions_requires_auth(app):
    with TestClient(app) as client:
        resp = client.get("/weather/conditions")
    assert resp.status_code == 401


def test_get_current_conditions_unavailable_when_store_empty(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/weather/conditions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["irradiance_w_m2"] is None


def test_get_current_conditions_returns_all_9_variables(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        # A real NWP window around "now" (I, T, RH, WS) plus a near-future
        # row (I_wrf) - the fixed "now" is 2026-07-16T06:30Z, daylight at
        # Nong Fab (~13:30 ICT), so clear-sky GHI/zenith/k-hat are all real,
        # non-null daylight values too.
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=2))
        app.state.real_data_store.insert_uv_observations(
            [_FakeUVObservation(observation_date=_FIXED_NOW.date(), uv_index=8.5, source="test-uv")]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/conditions", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    # I, T, RH, WS - straight off the inserted real NWP row.
    assert body["irradiance_w_m2"] == pytest.approx(500.0)
    assert body["temp_c"] == pytest.approx(30.0)
    assert body["relative_humidity_pct"] == pytest.approx(70.0)
    assert body["wind_speed_ms"] == pytest.approx((1.0**2 + 1.0**2) ** 0.5)
    # I_clr, cosθ, k-hat - computed, real daylight values (not None) at this
    # fixed daytime instant.
    assert body["clearsky_ghi_w_m2"] is not None and body["clearsky_ghi_w_m2"] > 0
    assert body["zenith_deg"] is not None
    assert -1.0 <= body["cos_zenith"] <= 1.0
    assert body["clear_sky_index"] is not None
    # I_wrf - the nearest real future row, not the same as `irradiance_w_m2`'s
    # own "now" timestamp.
    assert body["forecast_irradiance_w_m2"] == pytest.approx(500.0)
    assert body["forecast_valid_at"] is not None
    assert datetime.fromisoformat(body["forecast_valid_at"]) > _FIXED_NOW
    # UV - daily, from the separately-inserted observation.
    assert body["uv_index"] == pytest.approx(8.5)
    assert body["uv_observation_date"] == _FIXED_NOW.date().isoformat()


def test_get_current_conditions_uv_none_when_no_uv_data(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=1))
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/conditions", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True  # NWP data alone is enough to be "available"
    assert body["uv_index"] is None
    assert body["uv_observation_date"] is None


def test_get_current_conditions_uv_none_when_stale(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        app.state.real_data_store.insert_nwp_points(_real_points_around(_FIXED_NOW, hours_each_side=1))
        app.state.real_data_store.insert_uv_observations(
            [_FakeUVObservation(observation_date=(_FIXED_NOW - timedelta(days=5)).date(), uv_index=8.5, source="test-uv")]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/conditions", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["uv_index"] is None  # 5 days old > _UV_MAX_AGE_DAYS


def test_get_current_conditions_no_forecast_row_when_no_future_data(engine, tmp_path, monkeypatch):
    from nongfab_api.auth import create_access_token

    monkeypatch.setattr(routes_weather, "datetime", _FixedDatetime)
    app, settings = _app_with_file_backed_store(engine, tmp_path)

    with TestClient(app) as client:
        # Only past/current rows - no row after "now" to serve as I_wrf.
        app.state.real_data_store.insert_nwp_points(
            [p for p in _real_points_around(_FIXED_NOW, hours_each_side=2) if p.valid_time <= _FIXED_NOW]
        )
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/weather/conditions", headers={"Authorization": f"Bearer {token}"})

    body = resp.json()
    assert body["available"] is True
    assert body["forecast_irradiance_w_m2"] is None
    assert body["forecast_valid_at"] is None
