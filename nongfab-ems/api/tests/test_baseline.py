"""Direct tests for the shared real-or-synthetic day-conditions helper the
/performance, /simulate and /ws/live routes now build their baseline from."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from nongfab_forecast.local_store import RealDataStore

from nongfab_api.baseline import day_baseline_conditions


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


def test_day_baseline_conditions_synthetic_when_store_empty():
    idx, ssrd, temp, data_source = day_baseline_conditions(RealDataStore())
    assert data_source == "synthetic"
    assert len(idx) == 24 and len(ssrd) == 24 and len(temp) == 24


def test_day_baseline_conditions_real_when_today_fully_covered():
    store = RealDataStore()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # A full real NWP day for *today* (whatever real date this runs on) - so
    # coverage is 24/24 and the helper reports "real" deterministically,
    # without depending on the wall-clock hour it happens to run at.
    store.insert_nwp_points(
        [
            _FakeNWPPoint(
                valid_time=day_start + timedelta(hours=h), issue_time=day_start, ssrd_w_m2=500.0, temp2m_c=30.0,
                wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
            )
            for h in range(24)
        ]
    )
    idx, ssrd, temp, data_source = day_baseline_conditions(store)
    assert data_source == "real"
    assert len(idx) == 24
    assert float(ssrd[0]) == 500.0  # real seeded value flowed through
