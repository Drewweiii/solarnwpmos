"""Only covers _backfill_forecast_history - the other startup-backfill
functions (NWP/Himawari/UV/PVGIS) need real or mocked HTTP sources and
already have no dedicated test file (see ingestion_scheduler.py's own
docstring: "no existing test_ingestion_scheduler.py in this module to
extend" was true when the k-step/motion-vector work landed and still is
for those - covered indirectly via forecast/'s own test suite and the fact
this module still imports/type-checks/runs cleanly). This function is
different: no network involved (physics_baseline_series is a pure local
computation), so it's cheap to test directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import FORECAST_HISTORY_LOOKBACK_HOURS, GENERATED_POWER_BACKFILL_HOURS, GENERATED_POWER_HORIZON

from nongfab_api.ingestion_scheduler import (
    ZONES,
    _backfill_forecast_history,
    _backfill_generated_power_history,
    start_background_ingestion,
    stop_background_ingestion,
)


def _scheduler_settings(**overrides) -> SimpleNamespace:
    base = dict(
        backfill_lookback_days=1,
        himawari_poll_interval_seconds=600.0,
        nwp_poll_interval_seconds=3600.0,
        nwp_poll_forecast_hours=[1],
        retrain_interval_cold_seconds=3600.0,
        retrain_interval_warm_seconds=21600.0,
        retrain_warm_threshold_rows=500,
        enable_background_retraining=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_start_background_ingestion_spawns_retrain_task_when_enabled():
    store = RealDataStore()
    tasks = start_background_ingestion(store, _scheduler_settings(enable_background_retraining=True))
    try:
        names = {t.get_name() for t in tasks}
        assert "ingestion-retrain" in names
        assert "ingestion-poll-nwp" in names  # cheap polling always present
    finally:
        await stop_background_ingestion(tasks)


async def test_start_background_ingestion_skips_retrain_task_when_disabled():
    """The memory-heavy retrain loop is gated off, but the cheap GFS/Himawari
    polling that feeds the live dashboard readouts must still run - the whole
    point of splitting the two flags (2026-07-19)."""
    store = RealDataStore()
    tasks = start_background_ingestion(store, _scheduler_settings(enable_background_retraining=False))
    try:
        names = {t.get_name() for t in tasks}
        assert "ingestion-retrain" not in names
        assert "ingestion-poll-nwp" in names
        assert "ingestion-poll-himawari" in names
    finally:
        await stop_background_ingestion(tasks)


async def test_backfill_forecast_history_seeds_every_zone_and_horizon():
    store = RealDataStore()
    await _backfill_forecast_history(store)

    now = datetime.now(timezone.utc)
    for zone in ZONES:
        for horizon, lookback_hours in FORECAST_HISTORY_LOOKBACK_HOURS.items():
            rows = store.forecast_history_points(zone, horizon, since=now - timedelta(hours=lookback_hours))
            assert len(rows) > 0, f"expected seeded history for {zone}/{horizon}"


async def test_backfill_forecast_history_skips_a_pair_that_already_has_data():
    store = RealDataStore()
    now = datetime.now(timezone.utc)

    class _FakePoint:
        def __init__(self, timestamp):
            self.timestamp = timestamp
            self.pred = 12.3
            self.lower = None
            self.upper = None
            self.algorithm = None
            self.error = None

    store.record_forecast_points("GIS", "hour", now, [_FakePoint(now)])

    await _backfill_forecast_history(store)

    rows = store.forecast_history_points("GIS", "hour", since=now - timedelta(hours=24))
    # Only the one manually-seeded row - the backfill must not have piled 24
    # more physics-baseline rows on top of a pair that already had data.
    assert len(rows) == 1
    assert rows[0][1] == 12.3


async def test_backfill_generated_power_history_seeds_every_zone():
    store = RealDataStore()
    await _backfill_generated_power_history(store)

    now = datetime.now(timezone.utc)
    for zone in ZONES:
        rows = store.forecast_history_points(zone, GENERATED_POWER_HORIZON, since=now - timedelta(hours=GENERATED_POWER_BACKFILL_HOURS))
        assert len(rows) > 0, f"expected seeded generated-power history for {zone}"


async def test_backfill_generated_power_history_skips_a_zone_that_already_has_data():
    store = RealDataStore()
    now = datetime.now(timezone.utc)

    class _FakePoint:
        def __init__(self, timestamp):
            self.timestamp = timestamp
            self.pred = 55.0
            self.lower = None
            self.upper = None
            self.algorithm = None
            self.error = None

    store.record_forecast_points("GIS", GENERATED_POWER_HORIZON, now, [_FakePoint(now)])

    await _backfill_generated_power_history(store)

    rows = store.forecast_history_points("GIS", GENERATED_POWER_HORIZON, since=now - timedelta(hours=GENERATED_POWER_BACKFILL_HOURS))
    # Only the one manually-seeded row - the backfill must not have piled
    # more physics-baseline rows on top of a zone that already had data.
    assert len(rows) == 1
    assert rows[0][1] == 55.0
