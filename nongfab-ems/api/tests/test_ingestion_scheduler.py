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

from nongfab_api.ingestion_scheduler import ZONES, _backfill_forecast_history
from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import FORECAST_HISTORY_LOOKBACK_HOURS


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
