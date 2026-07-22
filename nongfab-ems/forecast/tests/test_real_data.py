from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
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
    motion_speed_kmh: float | None = None
    motion_direction_deg: float | None = None


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


def _seed_nwp_history_kstep(store: RealDataStore, n: int, lead_hour: int, base_issue: datetime, step: timedelta = timedelta(hours=6)) -> None:
    """Seeds `n` rows all at the same `lead_hour` bucket (valid_time = issue_time
    + lead_hour), issue_times `step` apart - mirrors real GFS cycles arriving
    periodically, each contributing one row per lead hour."""
    points = []
    for i in range(n):
        issue_time = base_issue + i * step
        valid_time = issue_time + timedelta(hours=lead_hour)
        ssrd = max(0.0, 700 * (1 - abs(valid_time.hour - 12) / 6))
        points.append(
            _FakeNWPPoint(
                valid_time=valid_time, issue_time=issue_time, ssrd_w_m2=ssrd, temp2m_c=28.0,
                wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
            )
        )
    store.insert_nwp_points(points)


def test_real_hour_frame_kstep_builds_expected_columns_above_minimum():
    store = RealDataStore()
    _seed_nwp_history_kstep(
        store, n=real_data.MIN_HOUR_ROWS_PER_LEAD + 2, lead_hour=3, base_issue=datetime(2026, 7, 1, tzinfo=timezone.utc)
    )

    X, y = real_data.real_hour_frame_kstep("GIS", store, lead_hour=3)
    assert list(X.columns) == ["ssrd_w_m2", "temp2m_c", "power_lag1", "clear_sky_ssrd_w_m2", "cloud_index"]
    assert len(X) == len(y) == real_data.MIN_HOUR_ROWS_PER_LEAD + 2
    assert (X["clear_sky_ssrd_w_m2"] >= 0).all()
    # no cloud history seeded - every row falls back to the documented neutral default
    assert (X["cloud_index"] == real_data._UNKNOWN_CLOUD_INDEX_DEFAULT).all()


def test_real_hour_frame_kstep_uses_real_cloud_index_near_issue_time():
    store = RealDataStore()
    lead_hour = 2
    base_issue = datetime(2026, 7, 1, 6, tzinfo=timezone.utc)
    _seed_nwp_history_kstep(store, n=real_data.MIN_HOUR_ROWS_PER_LEAD, lead_hour=lead_hour, base_issue=base_issue)
    # a real cloud reading exactly at the first row's own issue_time - later rows'
    # issue_times are 6h+ apart, well outside _CLOUD_INDEX_MAX_AGE_MINUTES
    store.insert_cloud_frames(
        [_FakeCloudFrame(observed_at=base_issue, nong_fab_cloud_opacity_pct=80.0, nong_fab_cloud_index=0.8, source="test")]
    )

    X, _ = real_data.real_hour_frame_kstep("GIS", store, lead_hour=lead_hour)
    assert X["cloud_index"].iloc[0] == pytest.approx(0.8)
    assert X["cloud_index"].iloc[-1] == real_data._UNKNOWN_CLOUD_INDEX_DEFAULT


def test_current_hour_conditions_kstep_includes_clear_sky_and_cloud_index():
    store = RealDataStore()
    lead_hour = 1
    issue_time = datetime(2026, 7, 1, 4, tzinfo=timezone.utc)
    valid_time = issue_time + timedelta(hours=lead_hour)
    store.insert_nwp_points(
        [
            _FakeNWPPoint(
                valid_time=valid_time, issue_time=issue_time, ssrd_w_m2=500.0, temp2m_c=28.0,
                wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
            )
        ]
    )

    row = real_data.current_hour_conditions_kstep("GIS", store, lead_hour=lead_hour, now=issue_time)
    assert list(row.columns) == ["ssrd_w_m2", "temp2m_c", "power_lag1", "clear_sky_ssrd_w_m2", "cloud_index"]
    assert row.iloc[0]["clear_sky_ssrd_w_m2"] >= 0
    assert row.iloc[0]["cloud_index"] == real_data._UNKNOWN_CLOUD_INDEX_DEFAULT


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
    assert list(df.columns) == real_data.MINUTE_FEATURE_COLS
    assert len(df) == real_data.MIN_MINUTE_ROWS + 5


def test_real_minute_frame_converts_motion_speed_direction_to_uv_components():
    store = RealDataStore()
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    # due east at 10 km/h: u (east) = 10, v (north) ~= 0
    frames = [
        _FakeCloudFrame(
            observed_at=start + timedelta(minutes=10 * i), nong_fab_cloud_opacity_pct=30.0, nong_fab_cloud_index=0.3,
            source="test", motion_speed_kmh=10.0, motion_direction_deg=90.0,
        )
        for i in range(real_data.MIN_MINUTE_ROWS)
    ]
    store.insert_cloud_frames(frames)

    df = real_data.real_minute_frame(store)
    # pytest.approx vs a bare pandas Series silently compares element-wise as
    # all-False (pandas' own __eq__ wins over ApproxScalar's) - .to_numpy() first.
    assert df["motion_u_kmh"].to_numpy() == pytest.approx(10.0, abs=1e-9)
    assert df["motion_v_kmh"].to_numpy() == pytest.approx(0.0, abs=1e-9)


def test_real_minute_frame_fills_missing_motion_with_zero():
    store = RealDataStore()
    _seed_cloud_history(store, n=real_data.MIN_MINUTE_ROWS, start=datetime(2026, 7, 1, tzinfo=timezone.utc))  # no motion set
    df = real_data.real_minute_frame(store)
    assert (df["motion_u_kmh"] == 0.0).all()
    assert (df["motion_v_kmh"] == 0.0).all()


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


def test_physics_baseline_series_historical_cloud_uses_matching_past_reading():
    """The core regression test for the 2026-07-19 fix: before this, a past
    timestamp's physics estimate only ever looked at the single most-recent
    cloud reading (or none at all) relative to wall-clock "now" - never that
    specific past hour's own real cloud cover, even when the store had one.
    use_historical_cloud=True changes that."""
    store = RealDataStore()
    # hour=6 UTC, not 12 - Nong Fab is ICT (UTC+7), so 12:00 UTC is 19:00
    # local (after sunset, clear-sky GHI=0 -> power=0 regardless of cloud,
    # which would make this test vacuously true). 06:00 UTC = 13:00 ICT,
    # solidly midday.
    past = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0) - timedelta(days=3)
    timestamps = pd.date_range(past, periods=1, freq="h", tz="UTC")

    store.insert_cloud_frames([
        _FakeCloudFrame(observed_at=past + timedelta(minutes=10), nong_fab_cloud_opacity_pct=90.0, nong_fab_cloud_index=0.9, source="test"),
    ])

    # Default (use_historical_cloud=False): that 3-day-old reading is nowhere
    # near wall-clock "now", so the max_cloud_age_minutes freshness check
    # rejects it - falls back to clear-sky, same as no cloud data at all.
    latest_only_result = real_data.physics_baseline_series("GIS", timestamps, store)
    clear_result = real_data.physics_baseline_series("GIS", timestamps, None)
    assert latest_only_result["pred"].iloc[0] == pytest.approx(clear_result["pred"].iloc[0])

    # use_historical_cloud=True looks up that timestamp's *own* nearby
    # reading instead of wall-clock freshness - finds the 90%-opacity frame
    # 10 minutes after it and attenuates accordingly.
    historical_result = real_data.physics_baseline_series("GIS", timestamps, store, use_historical_cloud=True)
    assert historical_result["pred"].iloc[0] < clear_result["pred"].iloc[0]


def test_physics_baseline_series_historical_cloud_falls_back_to_clearsky_without_match():
    store = RealDataStore()
    now = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)  # 13:00 ICT, midday
    timestamps = pd.date_range(now, periods=1, freq="h", tz="UTC")

    # A reading that exists but sits 10h away from the queried timestamp -
    # outside the historical match tolerance (2h), so it must not be used.
    store.insert_cloud_frames([
        _FakeCloudFrame(observed_at=now - timedelta(hours=10), nong_fab_cloud_opacity_pct=90.0, nong_fab_cloud_index=0.9, source="test"),
    ])

    clear_result = real_data.physics_baseline_series("GIS", timestamps, None)
    historical_result = real_data.physics_baseline_series("GIS", timestamps, store, use_historical_cloud=True)
    assert historical_result["pred"].iloc[0] == pytest.approx(clear_result["pred"].iloc[0])


def test_physics_baseline_series_historical_cloud_differs_per_timestamp():
    """Two timestamps a day apart but the same hour-of-day (so they share
    nearly the same clear-sky curve) with two very different real cloud
    readings must come out differently - proof use_historical_cloud looks up
    *each* timestamp's own match rather than one reading applied to all of
    them (which is exactly the old bug: backfill_generated_power_history and
    backfill_forecast_history both used one shared reading for an entire
    retrospective window)."""
    store = RealDataStore()
    base = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0) - timedelta(days=2)  # 13:00 ICT, midday
    cloudy_time = base
    clear_time = base + timedelta(days=1)
    timestamps = pd.DatetimeIndex([pd.Timestamp(cloudy_time), pd.Timestamp(clear_time)])

    store.insert_cloud_frames([
        _FakeCloudFrame(observed_at=cloudy_time, nong_fab_cloud_opacity_pct=95.0, nong_fab_cloud_index=0.95, source="test"),
        _FakeCloudFrame(observed_at=clear_time, nong_fab_cloud_opacity_pct=5.0, nong_fab_cloud_index=0.05, source="test"),
    ])

    result = real_data.physics_baseline_series("GIS", timestamps, store, use_historical_cloud=True)
    assert result["pred"].iloc[0] < result["pred"].iloc[1]


def _seed_full_day_nwp(store: RealDataStore, day_start: datetime) -> None:
    """24 hourly NWP rows covering `day_start` .. day_start+23h."""
    _seed_nwp_history(store, n=24, start=day_start, step=timedelta(hours=1))


def test_real_day_conditions_returns_full_day_from_real_nwp():
    store = RealDataStore()
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    day_start = now.replace(hour=0)
    _seed_full_day_nwp(store, day_start)

    idx, ssrd, temp = real_data.real_day_conditions(store, now=now)

    # Matches synthetic_day_irradiance_temp()'s shape exactly: one UTC calendar
    # day, 00:00-23:00 hourly.
    assert len(idx) == 24 and len(ssrd) == 24 and len(temp) == 24
    assert idx[0] == pd.Timestamp(day_start)
    assert idx[-1] == pd.Timestamp(day_start) + pd.Timedelta(hours=23)
    # Each slot round-trips the seeded real value (delta 0, well within tolerance)
    # - _seed_nwp_history peaks its ssrd bump at hour 12.
    assert ssrd[12] == pytest.approx(700.0)
    assert ssrd[6] == pytest.approx(0.0)
    assert np.isfinite(ssrd).all() and np.isfinite(temp).all()


def test_real_day_conditions_raises_on_empty_store():
    store = RealDataStore()
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_day_conditions(store, now=datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc))


def test_real_day_conditions_raises_when_coverage_too_thin():
    store = RealDataStore()
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    # Only 3 hourly rows near the start of the day - far below the 0.8 coverage
    # bar, so this must fall through to InsufficientHistoryError (the caller
    # then uses the synthetic generator) rather than stitch a whole day from
    # three scattered points.
    _seed_nwp_history(store, n=3, start=now.replace(hour=0), step=timedelta(hours=1))
    with pytest.raises(real_data.InsufficientHistoryError):
        real_data.real_day_conditions(store, now=now)


def test_real_day_conditions_interpolates_small_gaps():
    store = RealDataStore()
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    day_start = now.replace(hour=0)
    # A full day minus a 3-hour block (hours 10,11,12 dropped). With the 1.5h
    # match tolerance, slots 10 and 12 still match their 1h-away neighbours
    # (hours 9 and 13), so only slot 11 is a genuine gap - coverage stays 23/24
    # (>= 0.8), and slot 11 is interpolated rather than left NaN.
    points = []
    for hour in range(24):
        if hour in (10, 11, 12):
            continue
        t = day_start + timedelta(hours=hour)
        points.append(
            _FakeNWPPoint(
                valid_time=t, issue_time=day_start, ssrd_w_m2=500.0, temp2m_c=30.0,
                wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=75.0, source="test",
            )
        )
    store.insert_nwp_points(points)

    idx, ssrd, temp = real_data.real_day_conditions(store, now=now)
    assert len(idx) == 24
    assert np.isfinite(ssrd).all() and np.isfinite(temp).all()  # slot 11 interpolated, no NaN hole
