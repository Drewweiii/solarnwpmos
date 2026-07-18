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
