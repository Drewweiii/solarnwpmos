"""Soiling & Cleaning Advisor (2026-07-25): the daily roll-up in
soiling_service, the measured-soiling publication that replaces the loss model's
literature placeholder, and the /soiling/{zone} route's honest-empty behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nongfab_forecast.local_store import RealDataStore
from nongfab_simulation.loss_model import (
    DEFAULT_SOILING_PCT_LAND,
    DEFAULT_SOILING_PCT_MARINE,
    SOILING_SOURCE_LITERATURE,
    SOILING_SOURCE_MEASURED,
    clear_measured_soiling_pct,
    default_loss_factors,
    set_measured_soiling_pct,
)

from nongfab_api.config import Settings
from nongfab_api.main import create_app
from nongfab_api.soiling_service import (
    INLAND_SALT_EXPOSURE,
    MARINE_SALT_EXPOSURE,
    assess_zone,
    daily_conditions,
    refresh_measured_soiling,
    salt_exposure,
)


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


@dataclass
class _FakeAerosolPoint:
    valid_time: datetime
    aod_550nm: float | None
    dust: float | None
    pm2_5: float | None
    pm10: float | None
    source: str = "test-aq"


def _seed(store: RealDataStore, days: int = 30, precip_mm: float = 0.0, pm10: float = 50.0) -> None:
    """`days` days of hourly NWP + aerosol history ending now. A southerly
    (onshore, from the Gulf) humid wind so the salt index is non-trivial - the
    meteorological "from" convention means a wind FROM the south is one blowing
    northward, i.e. a POSITIVE v component (see features/soiling.py)."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    nwp = []
    aero = []
    for h in range(days * 24):
        t = now - timedelta(hours=h)
        nwp.append(
            _FakeNWPPoint(
                valid_time=t,
                issue_time=t,
                ssrd_w_m2=400.0,
                temp2m_c=30.0,
                wind10m_u_ms=0.0,
                wind10m_v_ms=5.0,  # blowing northward = wind FROM the south = onshore
                relative_humidity_pct=80.0,
                source="test-real",
                precip_mm=precip_mm,
            )
        )
        aero.append(_FakeAerosolPoint(valid_time=t, aod_550nm=0.2, dust=8.0, pm2_5=20.0, pm10=pm10))
    store.insert_nwp_points(nwp)
    store.insert_aerosol_points(aero)


@pytest.fixture(autouse=True)
def _clean_measured_soiling():
    """The measured-soiling override is process-level, so every test starts and
    ends with it cleared - otherwise one test's publication would leak into
    another's loss-factor assertions."""
    clear_measured_soiling_pct()
    yield
    clear_measured_soiling_pct()


def test_daily_conditions_rolls_hours_up_and_sums_rainfall():
    store = RealDataStore()
    _seed(store, days=5, precip_mm=1.0)
    days = daily_conditions(store, window_days=10)
    assert len(days) >= 5
    mid = days[len(days) // 2]
    assert mid.pm10_ug_m3 == pytest.approx(50.0)
    assert mid.dust_ug_m3 == pytest.approx(8.0)
    # 24 hourly rows of 1.0 mm each -> a 24 mm day (SUMMED, not averaged).
    assert mid.precip_mm == pytest.approx(24.0)
    # Onshore humid wind -> a real (non-zero) salt index.
    assert 0 < mid.salt_index <= 1


def test_daily_conditions_is_empty_without_both_stores():
    store = RealDataStore()
    assert daily_conditions(store) == []


def test_assess_zone_is_honestly_unavailable_with_no_history():
    store = RealDataStore()
    assessment = assess_zone(store, "GIS")
    assert assessment.available is False
    assert assessment.days_assessed == 0
    assert assessment.days_since_cleaning_rain is None
    assert assessment.series_loss_pct == ()


def test_assess_zone_reports_accumulation_over_a_dry_window():
    store = RealDataStore()
    _seed(store, days=20, precip_mm=0.0)
    a = assess_zone(store, "GIS")
    assert a.available is True
    assert a.days_assessed >= 20
    assert a.current_loss_pct > a.average_loss_pct > 0  # still climbing, never washed
    assert a.cleaning_events == 0
    assert a.days_since_cleaning_rain is None
    assert a.current_daily_rate_pct > 0
    assert a.days_until_trigger is None or a.days_until_trigger > 0
    assert len(a.series_loss_pct) == a.days_assessed


def test_rain_in_the_window_keeps_the_array_cleaner():
    dry = RealDataStore()
    _seed(dry, days=20, precip_mm=0.0)
    wet = RealDataStore()
    _seed(wet, days=20, precip_mm=1.0)  # 24 mm/day - a washing rain every day

    dry_a = assess_zone(dry, "GIS")
    wet_a = assess_zone(wet, "GIS")
    assert wet_a.average_loss_pct < dry_a.average_loss_pct
    assert wet_a.cleaning_events > 0
    assert wet_a.days_since_cleaning_rain == 0


def test_the_marine_jetty_zone_soils_faster_than_the_inland_zones():
    assert salt_exposure("Jetty") == MARINE_SALT_EXPOSURE
    assert salt_exposure("GIS") == INLAND_SALT_EXPOSURE
    store = RealDataStore()
    _seed(store, days=20, precip_mm=0.0)
    assert assess_zone(store, "Jetty").current_loss_pct > assess_zone(store, "GIS").current_loss_pct


def test_cost_of_soiling_only_appears_when_both_inputs_are_known():
    store = RealDataStore()
    _seed(store, days=20)
    priced = assess_zone(store, "GIS", annual_clean_energy_kwh=100_000.0, tariff_thb_per_kwh=4.0)
    assert priced.annual_energy_lost_kwh == pytest.approx(100_000.0 * priced.current_loss_pct / 100)
    assert priced.annual_cost_lost_thb == pytest.approx(priced.annual_energy_lost_kwh * 4.0)
    # No tariff -> energy only, never a guessed baht figure.
    unpriced = assess_zone(store, "GIS", annual_clean_energy_kwh=100_000.0)
    assert unpriced.annual_energy_lost_kwh is not None
    assert unpriced.annual_cost_lost_thb is None
    # No energy either -> both None.
    bare = assess_zone(store, "GIS")
    assert bare.annual_energy_lost_kwh is None
    assert bare.annual_cost_lost_thb is None


def test_loss_model_keeps_its_literature_default_until_something_is_published():
    assert default_loss_factors("GIS").soiling_pct == DEFAULT_SOILING_PCT_LAND
    assert default_loss_factors("GIS").soiling_source == SOILING_SOURCE_LITERATURE
    assert default_loss_factors("Jetty").soiling_pct == DEFAULT_SOILING_PCT_MARINE


def test_publishing_a_measurement_replaces_the_placeholder_and_is_labelled():
    set_measured_soiling_pct("GIS", 1.75)
    factors = default_loss_factors("GIS")
    assert factors.soiling_pct == 1.75
    assert factors.soiling_source == SOILING_SOURCE_MEASURED
    # Zones without a measurement are untouched.
    assert default_loss_factors("Jetty").soiling_source == SOILING_SOURCE_LITERATURE


def test_set_measured_soiling_rejects_an_impossible_percentage():
    with pytest.raises(ValueError):
        set_measured_soiling_pct("GIS", 150.0)


def test_refresh_publishes_for_every_zone_once_history_exists():
    store = RealDataStore()
    assert refresh_measured_soiling(store) == {}  # nothing to publish yet
    assert default_loss_factors("GIS").soiling_source == SOILING_SOURCE_LITERATURE

    _seed(store, days=20)
    published = refresh_measured_soiling(store)
    assert set(published) == {"GIS", "ISB", "Jetty"}
    assert default_loss_factors("GIS").soiling_pct == pytest.approx(published["GIS"])
    assert default_loss_factors("GIS").soiling_source == SOILING_SOURCE_MEASURED


# --- route ------------------------------------------------------------------


def _file_backed_app(engine, tmp_path):
    """A file-backed real_data_store, for the same thread-affinity reason
    test_routes_weather documents on its own helper."""
    settings = Settings(
        jwt_secret_key="test-secret",
        seed_demo_users=True,
        enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    return create_app(settings=settings, engine=engine), settings


def test_soiling_route_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/soiling/GIS").status_code == 401


def test_soiling_route_404s_on_an_unknown_zone(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/soiling/Nowhere", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_soiling_route_reports_unavailable_with_a_reason_when_history_is_empty(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/soiling/GIS", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["loss_model_soiling_source"] == "literature-default"
    assert body["series_loss_pct"] == []


def test_soiling_route_returns_the_assessment_once_history_exists(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        _seed(app.state.real_data_store, days=20)
        token = create_access_token("tester", "viewer", settings, app.state.deploy_id)
        resp = client.get("/soiling/Jetty", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["zone"] == "Jetty"
    assert body["days_assessed"] >= 20
    assert body["current_loss_pct"] > 0
    assert body["cleaning_trigger_pct"] > 0
    assert len(body["series_days"]) == len(body["series_loss_pct"]) == body["days_assessed"]
    # The route prices the loss against the facility's own implied tariff (real
    # user-stated cost / real load), so both figures must be present here.
    assert body["annual_energy_lost_kwh"] > 0
    assert body["annual_cost_lost_thb"] > 0
