from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from nongfab_forecast import real_data
from nongfab_forecast.local_store import RealDataStore


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


@dataclass
class _FakeCloudFrame:
    observed_at: datetime
    nong_fab_cloud_opacity_pct: float
    nong_fab_cloud_index: float
    source: str


def _seed_nwp_history(store: RealDataStore, n: int, start: datetime, step: timedelta = timedelta(hours=1)) -> None:
    points = []
    for i in range(n):
        t = start + i * step
        hour_of_day = t.hour
        ssrd = max(0.0, 700 * (1 - abs(hour_of_day - 12) / 6))  # a simple daytime bump, not flat/degenerate
        points.append(
            _FakeNWPPoint(
                valid_time=t, issue_time=start, ssrd_w_m2=ssrd, temp2m_c=28.0 + (i % 5),
                wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
            )
        )
    store.insert_nwp_points(points)


def _seed_cloud_history(store: RealDataStore, n: int, start: datetime, step: timedelta = timedelta(minutes=10)) -> None:
    frames = [
        _FakeCloudFrame(observed_at=start + i * step, nong_fab_cloud_opacity_pct=30.0 + (i % 10), nong_fab_cloud_index=0.3, source="test")
        for i in range(n)
    ]
    store.insert_cloud_frames(frames)


def test_pv_params_for_zone_uses_capacity_derived_fallback():
    params = real_data.pv_params_for_zone("GIS")
    assert params.beta_kw_per_wm2 > 0


def test_pv_params_for_zone_raises_for_unknown_zone():
    with pytest.raises(ValueError):
        real_data.pv_params_for_zone("Nowhere")


def test_real_hour_frame_raises_below_minimum_rows():
    store = RealDataStore()
    _seed_nwp_history(store, n=5, start=datetime(2026, 7, 1, tzinfo=timezone.utc))
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_hour_frame("GIS", store)


def test_real_hour_frame_builds_expected_columns_above_minimum():
    store = RealDataStore()
    _seed_nwp_history(store, n=real_data.MIN_HOUR_ROWS + 5, start=datetime(2026, 7, 1, tzinfo=timezone.utc))

    X, y = real_data.real_hour_frame("GIS", store)
    assert list(X.columns) == ["ssrd_w_m2", "temp2m_c", "power_lag1"]
    assert len(X) == len(y) == real_data.MIN_HOUR_ROWS + 5
    assert (y >= 0).all()  # predict_power_kw clips at 0
    # daytime rows (real ssrd > 0) should have nonzero predicted power
    assert (y[X["ssrd_w_m2"] > 0] > 0).any()


def test_real_hour_frame_dedupes_by_valid_time_keeping_latest():
    store = RealDataStore()
    t = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    _seed_nwp_history(store, n=real_data.MIN_HOUR_ROWS, start=t)
    # re-insert the same valid_time with a different value under a distinct issue_time
    # (a later GFS cycle re-forecasting the same valid hour) - dedup should keep one row per valid_time
    store.insert_nwp_points([
        _FakeNWPPoint(
            valid_time=t, issue_time=t + timedelta(hours=6), ssrd_w_m2=999.0, temp2m_c=28.0,
            wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
        )
    ])

    X, y = real_data.real_hour_frame("GIS", store)
    assert len(X) == real_data.MIN_HOUR_ROWS  # not +1 - the duplicate valid_time collapsed to one row


def test_real_day_frame_raises_below_minimum_and_builds_indexed_frame_above():
    store = RealDataStore()
    _seed_nwp_history(store, n=10, start=datetime(2026, 7, 1, tzinfo=timezone.utc))
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_day_frame("GIS", store)

    _seed_nwp_history(store, n=real_data.MIN_DAY_ROWS, start=datetime(2026, 7, 5, tzinfo=timezone.utc))
    df = real_data.real_day_frame("GIS", store)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert list(df.columns) == ["power_kw", "ssrd_w_m2", "temp2m_c"]
    assert df.index.is_monotonic_increasing


def test_real_future_regressors_filters_to_rows_after_now():
    store = RealDataStore()
    now = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
    _seed_nwp_history(store, n=5, start=now - timedelta(hours=5))  # all in the past
    _seed_nwp_history(store, n=5, start=now + timedelta(hours=1))  # all in the future

    future = real_data.real_future_regressors(store, now=now)
    assert len(future) == 5
    assert (future.index > pd.Timestamp(now)).all()


def test_real_future_regressors_raises_when_store_empty():
    store = RealDataStore()
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_future_regressors(store)


def test_current_hour_conditions_picks_nearest_row_and_uses_previous_rows_power_as_lag():
    store = RealDataStore()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    store.insert_nwp_points([
        _FakeNWPPoint(
            valid_time=base, issue_time=base, ssrd_w_m2=500.0, temp2m_c=28.0,
            wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
        ),
        _FakeNWPPoint(
            valid_time=base + timedelta(hours=1), issue_time=base, ssrd_w_m2=600.0, temp2m_c=29.0,
            wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
        ),
    ])

    row = real_data.current_hour_conditions("GIS", store, now=base + timedelta(hours=1))
    assert row.iloc[0]["ssrd_w_m2"] == 600.0
    expected_lag = real_data.pv_conversion.predict_power_kw(500.0, 28.0, real_data.pv_params_for_zone("GIS"))
    assert row.iloc[0]["power_lag1"] == pytest.approx(float(expected_lag))


def test_current_hour_conditions_first_row_has_zero_lag():
    store = RealDataStore()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    store.insert_nwp_points([
        _FakeNWPPoint(
            valid_time=base, issue_time=base, ssrd_w_m2=500.0, temp2m_c=28.0,
            wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
        ),
    ])
    row = real_data.current_hour_conditions("GIS", store, now=base)
    assert row.iloc[0]["power_lag1"] == 0.0


def test_real_minute_frame_raises_below_minimum_rows():
    store = RealDataStore()
    _seed_cloud_history(store, n=5, start=datetime(2026, 7, 1, tzinfo=timezone.utc))
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_minute_frame(store)


def test_real_minute_frame_builds_expected_columns_above_minimum():
    store = RealDataStore()
    _seed_cloud_history(store, n=real_data.MIN_MINUTE_ROWS + 5, start=datetime(2026, 7, 1, tzinfo=timezone.utc))
    df = real_data.real_minute_frame(store)
    assert list(df.columns) == ["cloud_opacity_pct", "cloud_index"]
    assert len(df) == real_data.MIN_MINUTE_ROWS + 5


def test_recent_minute_window_returns_last_n_rows_in_order():
    store = RealDataStore()
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    _seed_cloud_history(store, n=real_data.MIN_MINUTE_ROWS + 10, start=start)

    window = real_data.recent_minute_window(store, lookback=12)
    assert len(window) == 12
    # the last seeded opacity value should be the last row of the window
    full = real_data.real_minute_frame(store)
    assert window["cloud_opacity_pct"].tolist() == full["cloud_opacity_pct"].tolist()[-12:]


def test_physics_baseline_series_uses_clearsky_when_no_recent_cloud_data():
    store = RealDataStore()
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    timestamps = pd.date_range(now, periods=3, freq="h", tz="UTC")

    result = real_data.physics_baseline_series("GIS", timestamps, store)
    assert list(result.columns) == ["pred"]
    assert (result["pred"] >= 0).all()


def test_physics_baseline_series_attenuates_with_fresh_cloud_data():
    store = RealDataStore()
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    timestamps = pd.date_range(now, periods=1, freq="h", tz="UTC")

    clear_result = real_data.physics_baseline_series("GIS", timestamps, None)

    store.insert_cloud_frames([
        _FakeCloudFrame(observed_at=datetime.now(timezone.utc), nong_fab_cloud_opacity_pct=90.0, nong_fab_cloud_index=0.9, source="test"),
    ])
    cloudy_result = real_data.physics_baseline_series("GIS", timestamps, store)

    assert cloudy_result["pred"].iloc[0] <= clear_result["pred"].iloc[0]


def test_physics_baseline_series_ignores_stale_cloud_data():
    store = RealDataStore()
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    timestamps = pd.date_range(now, periods=1, freq="h", tz="UTC")

    stale_time = datetime.now(timezone.utc) - timedelta(hours=5)
    store.insert_cloud_frames([
        _FakeCloudFrame(observed_at=stale_time, nong_fab_cloud_opacity_pct=90.0, nong_fab_cloud_index=0.9, source="test"),
    ])

    clear_result = real_data.physics_baseline_series("GIS", timestamps, None)
    stale_result = real_data.physics_baseline_series("GIS", timestamps, store, max_cloud_age_minutes=30.0)
    assert stale_result["pred"].iloc[0] == pytest.approx(clear_result["pred"].iloc[0])
