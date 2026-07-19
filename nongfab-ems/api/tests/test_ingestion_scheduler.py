"""Mostly covers _backfill_forecast_history and _backfill_generated_power_history
- the other startup-backfill functions (NWP/Himawari/UV/PVGIS) need real or
mocked HTTP sources and already have no dedicated test file (see
ingestion_scheduler.py's own docstring: "no existing
test_ingestion_scheduler.py in this module to extend" was true when the
k-step/motion-vector work landed and still is for those - covered indirectly
via forecast/'s own test suite and the fact this module still imports/type-
checks/runs cleanly).

_backfill_forecast_history is pure local computation (no network at all),
cheap to test directly as-is. _backfill_generated_power_history used to be
the same, but as of 2026-07-19 it calls _backfill_himawari_bounded first
(a real Himawari historical fetch, so physics_baseline_series has real
per-hour cloud data to use for the actual-power estimate - see that
function's own docstring) - every test below that exercises
_backfill_generated_power_history monkeypatches _backfill_himawari_bounded
to a no-op so these stay fast/network-free like before; the fetch's own
wiring (called vs. skipped) is covered separately, not its real HTTP
content, same "no mocked-HTTP test file for this yet" scope line as NWP/UV/
PVGIS above.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import FORECAST_HISTORY_LOOKBACK_HOURS, GENERATED_POWER_BACKFILL_HOURS, GENERATED_POWER_HORIZON

from nongfab_api import ingestion_scheduler
from nongfab_api.ingestion_scheduler import ZONES, _backfill_forecast_history, _backfill_generated_power_history


async def _no_op_himawari_bounded(store, days):
    pass


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


async def test_backfill_generated_power_history_seeds_every_zone(monkeypatch):
    monkeypatch.setattr(ingestion_scheduler, "_backfill_himawari_bounded", _no_op_himawari_bounded)
    store = RealDataStore()
    await _backfill_generated_power_history(store)

    now = datetime.now(timezone.utc)
    for zone in ZONES:
        rows = store.forecast_history_points(zone, GENERATED_POWER_HORIZON, since=now - timedelta(hours=GENERATED_POWER_BACKFILL_HOURS))
        assert len(rows) > 0, f"expected seeded generated-power history for {zone}"


async def test_backfill_generated_power_history_skips_a_zone_that_already_has_data(monkeypatch):
    monkeypatch.setattr(ingestion_scheduler, "_backfill_himawari_bounded", _no_op_himawari_bounded)
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


async def test_backfill_generated_power_history_fetches_historical_cloud_when_a_zone_needs_seeding(monkeypatch):
    calls = []

    async def _tracking_himawari_bounded(store, days):
        calls.append(days)

    monkeypatch.setattr(ingestion_scheduler, "_backfill_himawari_bounded", _tracking_himawari_bounded)
    store = RealDataStore()

    await _backfill_generated_power_history(store)

    assert calls == [ingestion_scheduler._GENERATED_POWER_CLOUD_LOOKBACK_DAYS]


async def test_backfill_generated_power_history_skips_historical_cloud_fetch_when_every_zone_already_has_data(monkeypatch):
    async def _failing_himawari_bounded(store, days):
        raise AssertionError("should not fetch historical cloud data when no zone needs seeding")

    monkeypatch.setattr(ingestion_scheduler, "_backfill_himawari_bounded", _failing_himawari_bounded)
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

    for zone in ZONES:
        store.record_forecast_points(zone, GENERATED_POWER_HORIZON, now, [_FakePoint(now)])

    await _backfill_generated_power_history(store)  # must not raise
