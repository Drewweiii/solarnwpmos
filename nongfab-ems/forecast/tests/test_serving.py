from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from nongfab_forecast.local_store import RealDataStore
from nongfab_forecast.serving import (
    FALLBACK_PI_HALF_WIDTH_PCT,
    FORECAST_HISTORY_LOOKBACK_HOURS,
    ModelNotTrainedError,
    UnknownHorizonError,
    UnknownZoneError,
    _ceil_to,
    backfill_forecast_history,
    get_forecast_with_fallback,
    get_latest_forecast,
    validate_horizon,
    validate_zone,
)


@dataclass
class _FakePoint:
    timestamp: datetime
    pred: float
    lower: float | None
    upper: float | None
    algorithm: str | None
    error: float | None
    candidate_errors: dict[str, float] | None = None


def test_validate_zone_accepts_known_zones():
    for zone in ("GIS", "ISB", "Jetty"):
        assert validate_zone(zone) == zone


def test_validate_zone_rejects_unknown_zone():
    with pytest.raises(UnknownZoneError):
        validate_zone("Nowhere")


def test_validate_horizon_accepts_known_horizons():
    for horizon in ("minute", "hour", "day"):
        assert validate_horizon(horizon) == horizon


def test_validate_horizon_rejects_unknown_horizon():
    with pytest.raises(UnknownHorizonError):
        validate_horizon("century")


def test_get_latest_forecast_raises_model_not_trained_when_none_registered(tmp_path, monkeypatch):
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    with pytest.raises(ModelNotTrainedError):
        get_latest_forecast("GIS", "hour")


def test_get_latest_forecast_validates_before_touching_mlflow():
    # unknown zone/horizon should raise immediately, without needing a valid
    # MLflow tracking URI configured at all
    with pytest.raises(UnknownZoneError):
        get_latest_forecast("Nowhere", "hour")
    with pytest.raises(UnknownHorizonError):
        get_latest_forecast("GIS", "century")


def test_get_forecast_with_fallback_gives_the_physics_baseline_a_bounded_pi(tmp_path, monkeypatch):
    """2026-07-16: the user asked for *some* prediction-interval band on the
    dashboard even while running the no-ML physics fallback (previously
    lower/upper were always None here - see FALLBACK_PI_HALF_WIDTH_PCT's own
    docstring for why this is a fixed approximation, not a real PI)."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    result = get_forecast_with_fallback("GIS", "hour")
    assert result.model_type == "physics_baseline"
    for point in result.points:
        assert point.lower is not None
        assert point.upper is not None
        assert point.lower <= point.pred <= point.upper
        assert point.lower == pytest.approx(max(0.0, point.pred * (1 - FALLBACK_PI_HALF_WIDTH_PCT)))
        assert point.upper == pytest.approx(point.pred * (1 + FALLBACK_PI_HALF_WIDTH_PCT))
        # no ML model ran at all on this path - algorithm/error must stay None
        # rather than claim a competition result that never happened.
        assert point.algorithm is None
        assert point.error is None


def test_ceil_to_rounds_up_to_the_next_hour_boundary():
    dt = datetime(2026, 7, 17, 14, 23, 7, tzinfo=timezone.utc)
    assert _ceil_to(dt, timedelta(hours=1)) == datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)


def test_ceil_to_leaves_an_exact_boundary_unchanged():
    dt = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)
    assert _ceil_to(dt, timedelta(hours=1)) == dt


def test_ceil_to_rounds_up_to_the_next_ten_minute_boundary():
    dt = datetime(2026, 7, 17, 14, 23, 7, tzinfo=timezone.utc)
    assert _ceil_to(dt, timedelta(minutes=10)) == datetime(2026, 7, 17, 14, 30, 0, tzinfo=timezone.utc)


def test_get_forecast_with_fallback_timestamps_land_on_clean_hour_boundaries(tmp_path, monkeypatch):
    """2026-07-16: the dashboard's x-axis kept visibly shifting by a few
    seconds on every 60s auto-refresh poll, because the forecast timestamp
    grid was anchored directly to the unrounded datetime.now(). Regression
    test: every hour/day-horizon point should now land exactly on :00."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    for horizon in ("hour", "day"):
        result = get_forecast_with_fallback("GIS", horizon)
        for point in result.points:
            assert point.timestamp.minute == 0
            assert point.timestamp.second == 0
            assert point.timestamp.microsecond == 0


def test_get_forecast_with_fallback_minute_timestamps_land_on_ten_minute_boundaries(tmp_path, monkeypatch):
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    result = get_forecast_with_fallback("GIS", "minute")
    for point in result.points:
        assert point.timestamp.minute % 10 == 0
        assert point.timestamp.second == 0
        assert point.timestamp.microsecond == 0


def test_get_forecast_with_fallback_timestamps_are_stable_across_repeated_calls_within_the_same_window(tmp_path, monkeypatch):
    """Regression test for the actual bug report: two calls a few seconds
    apart (simulating two dashboard polls) should produce the *same*
    timestamp grid, not one shifted by however many seconds elapsed."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    first = get_forecast_with_fallback("GIS", "hour")
    second = get_forecast_with_fallback("GIS", "hour")
    assert [p.timestamp for p in first.points] == [p.timestamp for p in second.points]


def test_get_forecast_with_fallback_includes_a_point_recorded_earlier_for_an_hour_now_in_the_past(tmp_path, monkeypatch):
    """The whole point of persisting forecast issuances: an hour that has
    already passed should still show up in the response if it was recorded
    earlier - not just whatever this particular call computes going
    forward. Regression test for the user's 2026-07-18 report that the
    Forecast line/Prediction interval band vanished for any past hour, even
    on a browser tab that had never been open before (i.e. nothing client-
    side to have remembered it) - this is the server-side fix for that.
    """
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    store = RealDataStore()
    now = datetime.now(timezone.utc)
    past_target = _ceil_to(now, timedelta(hours=1)) - timedelta(hours=2)
    store.record_forecast_points(
        "GIS", "hour", now - timedelta(hours=3),
        [_FakePoint(timestamp=past_target, pred=42.0, lower=30.0, upper=50.0, algorithm=None, error=None)],
    )

    result = get_forecast_with_fallback("GIS", "hour", store=store)

    matched = next((p for p in result.points if p.timestamp == past_target), None)
    assert matched is not None
    assert matched.pred == 42.0


def test_get_forecast_with_fallback_carries_candidate_errors_for_a_past_point(tmp_path, monkeypatch):
    """candidate_errors (every hour-ahead candidate's own RMSE, not just the
    winner's) must survive the persist-then-merge round trip the same way
    algorithm/error already do - the Model Competition panel reads it off a
    past point exactly like the main chart's per-model error lines do."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    store = RealDataStore()
    now = datetime.now(timezone.utc)
    past_target = _ceil_to(now, timedelta(hours=1)) - timedelta(hours=2)
    store.record_forecast_points(
        "GIS", "hour", now - timedelta(hours=3),
        [
            _FakePoint(
                timestamp=past_target, pred=42.0, lower=30.0, upper=50.0, algorithm="lightgbm", error=1.2,
                candidate_errors={"lightgbm": 1.2, "random_forest": 1.6, "sum_k_lstm": 1.4},
            )
        ],
    )

    result = get_forecast_with_fallback("GIS", "hour", store=store)

    matched = next(p for p in result.points if p.timestamp == past_target)
    assert matched.candidate_errors == {"lightgbm": 1.2, "random_forest": 1.6, "sum_k_lstm": 1.4}


def test_get_forecast_with_fallback_lets_a_newer_issuance_overwrite_an_older_one(tmp_path, monkeypatch):
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    store = RealDataStore()
    now = datetime.now(timezone.utc)
    target = _ceil_to(now, timedelta(hours=1))
    store.record_forecast_points(
        "GIS", "hour", now - timedelta(hours=1),
        [_FakePoint(timestamp=target, pred=999.0, lower=900.0, upper=1000.0, algorithm=None, error=None)],
    )

    result = get_forecast_with_fallback("GIS", "hour", store=store)

    matched = next(p for p in result.points if p.timestamp == target)
    assert matched.pred != 999.0  # this call's own freshly-computed value won, not the stale seeded one


def test_get_forecast_with_fallback_does_not_persist_minute_horizon(tmp_path, monkeypatch):
    """minute-ahead has its own dedicated small panel, not the Day-ahead/
    Intra-day toggle chart this fix was reported against - out of scope."""
    db_path = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db_path}")
    store = RealDataStore()
    get_forecast_with_fallback("GIS", "minute", store=store)
    assert store.counts()["forecast_history"] == 0


def test_backfill_forecast_history_seeds_the_full_lookback_window():
    """Regression test for the user's second 2026-07-18 follow-up: right
    after a fresh deploy/restart, forecast_history is genuinely empty (see
    local_store.py's ephemeral-storage docstring), so a request landing
    seconds later still showed a blank past even with _persist_and_merge_
    history in place - that function only stops history from being *lost
    going forward*, it can't retroactively show history that was never
    computed. This backfill closes that specific gap."""
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    store = RealDataStore()

    inserted = backfill_forecast_history("GIS", "hour", store, now=now)

    assert inserted == FORECAST_HISTORY_LOOKBACK_HOURS["hour"]
    rows = store.forecast_history_points("GIS", "hour", since=now - timedelta(hours=FORECAST_HISTORY_LOOKBACK_HOURS["hour"]))
    assert len(rows) == FORECAST_HISTORY_LOOKBACK_HOURS["hour"]
    # physics-baseline only - no ML model ran, so algorithm must stay honest
    for row in rows:
        assert row[4] is None  # algorithm


def test_backfill_forecast_history_covers_hours_strictly_before_now():
    now = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    store = RealDataStore()
    backfill_forecast_history("GIS", "day", store, now=now)
    rows = store.forecast_history_points("GIS", "day", since=now - timedelta(hours=FORECAST_HISTORY_LOOKBACK_HOURS["day"]))
    for target_time, *_ in rows:
        assert datetime.fromisoformat(target_time) < now


def test_backfill_forecast_history_is_a_noop_for_minute_horizon():
    store = RealDataStore()
    inserted = backfill_forecast_history("GIS", "minute", store, now=datetime.now(timezone.utc))
    assert inserted == 0
    assert store.counts()["forecast_history"] == 0
