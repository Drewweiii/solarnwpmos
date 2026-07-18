from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from nongfab_forecast.local_store import RealDataStore, default_db_path


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


@dataclass
class _FakeUVObservation:
    observation_date: object
    uv_index: float
    source: str


def test_default_db_path_is_in_memory_unless_env_var_set(monkeypatch):
    monkeypatch.delenv("NONGFAB_REAL_DATA_DB", raising=False)
    assert default_db_path() == ":memory:"

    monkeypatch.setenv("NONGFAB_REAL_DATA_DB", "/tmp/whatever.db")
    assert default_db_path() == "/tmp/whatever.db"


def test_store_starts_empty():
    store = RealDataStore()
    assert store.counts() == {"nwp_history": 0, "cloud_history": 0, "uv_history": 0, "forecast_history": 0}


def test_insert_and_read_nwp_points_roundtrips():
    store = RealDataStore()
    points = [
        _FakeNWPPoint(
            valid_time=datetime(2026, 7, 14, h, tzinfo=timezone.utc), issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
            ssrd_w_m2=100.0 + h, temp2m_c=28.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=80.0, source="test",
        )
        for h in range(3)
    ]
    inserted = store.insert_nwp_points(points)
    assert inserted == 3

    df = store.nwp_history_df()
    assert len(df) == 3
    assert list(df["ssrd_w_m2"]) == [100.0, 101.0, 102.0]
    assert df["valid_time"].is_monotonic_increasing


def test_insert_nwp_points_upserts_on_valid_time_issue_time_source():
    store = RealDataStore()
    p1 = _FakeNWPPoint(
        valid_time=datetime(2026, 7, 14, 1, tzinfo=timezone.utc), issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        ssrd_w_m2=100.0, temp2m_c=28.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=80.0, source="test",
    )
    store.insert_nwp_points([p1])
    p1_updated = _FakeNWPPoint(
        valid_time=p1.valid_time, issue_time=p1.issue_time,
        ssrd_w_m2=999.0, temp2m_c=28.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=80.0, source="test",
    )
    store.insert_nwp_points([p1_updated])

    df = store.nwp_history_df()
    assert len(df) == 1
    assert df.iloc[0]["ssrd_w_m2"] == 999.0


def test_count_nwp_rows_by_source_counts_only_the_matching_source():
    store = RealDataStore()
    gfs_point = _FakeNWPPoint(
        valid_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc), issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
        ssrd_w_m2=100.0, temp2m_c=28.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=80.0, source="gfs-noaa",
    )
    pvgis_points = [
        _FakeNWPPoint(
            valid_time=datetime(2020, 1, 1, h, tzinfo=timezone.utc), issue_time=datetime(2020, 1, 1, h, tzinfo=timezone.utc),
            ssrd_w_m2=200.0, temp2m_c=25.0, wind10m_u_ms=2.0, wind10m_v_ms=0.0, relative_humidity_pct=70.0, source="pvgis-era5",
        )
        for h in range(2)
    ]
    store.insert_nwp_points([gfs_point, *pvgis_points])

    assert store.count_nwp_rows_by_source("pvgis-era5") == 2
    assert store.count_nwp_rows_by_source("gfs-noaa") == 1
    assert store.count_nwp_rows_by_source("nonexistent-source") == 0


def test_insert_and_read_cloud_frames_roundtrips():
    store = RealDataStore()
    frames = [
        _FakeCloudFrame(
            observed_at=datetime(2026, 7, 14, 0, m, tzinfo=timezone.utc),
            nong_fab_cloud_opacity_pct=50.0 + m, nong_fab_cloud_index=0.5, source="test",
        )
        for m in (0, 10, 20)
    ]
    inserted = store.insert_cloud_frames(frames)
    assert inserted == 3

    df = store.cloud_history_df()
    assert len(df) == 3
    assert df["observed_at"].is_monotonic_increasing
    assert df["motion_speed_kmh"].isna().all()  # not set on these frames


def test_insert_cloud_frames_stores_motion_when_present():
    store = RealDataStore()
    frames = [
        _FakeCloudFrame(
            observed_at=datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc), nong_fab_cloud_opacity_pct=50.0,
            nong_fab_cloud_index=0.5, source="test", motion_speed_kmh=12.5, motion_direction_deg=270.0,
        ),
    ]
    store.insert_cloud_frames(frames)

    df = store.cloud_history_df()
    assert df.iloc[0]["motion_speed_kmh"] == 12.5
    assert df.iloc[0]["motion_direction_deg"] == 270.0


def test_insert_cloud_frames_accepts_frames_without_motion_attributes():
    """Old-style test doubles (no motion_speed_kmh/motion_direction_deg
    attributes at all, not just None) must still work - getattr(..., None),
    not a hard requirement - see insert_cloud_frames' own docstring."""
    @dataclass
    class _BareCloudFrame:
        observed_at: datetime
        nong_fab_cloud_opacity_pct: float
        nong_fab_cloud_index: float
        source: str

    store = RealDataStore()
    bare_frame = _BareCloudFrame(
        observed_at=datetime(2026, 7, 14, tzinfo=timezone.utc), nong_fab_cloud_opacity_pct=10.0, nong_fab_cloud_index=0.1, source="test"
    )
    store.insert_cloud_frames([bare_frame])
    df = store.cloud_history_df()
    assert len(df) == 1
    assert df.iloc[0]["motion_speed_kmh"] is None or pd.isna(df.iloc[0]["motion_speed_kmh"])


def test_cloud_history_df_handles_mixed_timestamp_precision():
    """Found live 2026-07-18 while building GET /weather/clouds: a row whose
    observed_at came from `datetime.now()` (microseconds present) mixed with
    a row whose observed_at didn't (a fixed poll-tick timestamp, the normal
    case for real Himawari frames) crashed `cloud_history_df()` with a
    pandas ValueError - `pd.to_datetime(..., utc=True)` without an explicit
    `format=` infers one fixed precision from the first row and rejects any
    other row that doesn't match it exactly. Regression test for the
    `format="ISO8601"` fix, which tolerates both."""
    store = RealDataStore()
    store.insert_cloud_frames(
        [
            _FakeCloudFrame(
                observed_at=datetime(2026, 7, 14, 0, 0, 0, tzinfo=timezone.utc),  # no microseconds
                nong_fab_cloud_opacity_pct=40.0, nong_fab_cloud_index=0.4, source="test",
            ),
            _FakeCloudFrame(
                observed_at=datetime(2026, 7, 14, 0, 10, 0, 498139, tzinfo=timezone.utc),  # microseconds present
                nong_fab_cloud_opacity_pct=45.0, nong_fab_cloud_index=0.45, source="test",
            ),
        ]
    )
    df = store.cloud_history_df()
    assert len(df) == 2
    assert df["observed_at"].is_monotonic_increasing


def test_latest_cloud_observation_returns_none_when_empty():
    store = RealDataStore()
    assert store.latest_cloud_observation() is None


def test_latest_cloud_observation_returns_most_recent_row():
    store = RealDataStore()
    frames = [
        _FakeCloudFrame(
            observed_at=datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc), nong_fab_cloud_opacity_pct=10.0, nong_fab_cloud_index=0.1, source="test"
        ),
        _FakeCloudFrame(
            observed_at=datetime(2026, 7, 14, 0, 10, tzinfo=timezone.utc), nong_fab_cloud_opacity_pct=90.0, nong_fab_cloud_index=0.9, source="test"
        ),
    ]
    store.insert_cloud_frames(frames)

    observed_at, opacity, index = store.latest_cloud_observation()
    assert observed_at == datetime(2026, 7, 14, 0, 10, tzinfo=timezone.utc)
    assert opacity == 90.0
    assert index == 0.9


def test_insert_and_read_uv_observations_roundtrips():
    from datetime import date

    store = RealDataStore()
    obs = [_FakeUVObservation(observation_date=date(2026, 7, 1 + i), uv_index=5.0 + i, source="test") for i in range(2)]
    inserted = store.insert_uv_observations(obs)
    assert inserted == 2

    df = store.uv_history_df()
    assert len(df) == 2


def test_file_backed_store_persists_across_reconnects(tmp_path):
    db_path = str(tmp_path / "real_data.db")
    store1 = RealDataStore(db_path=db_path)
    store1.insert_nwp_points([
        _FakeNWPPoint(
            valid_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc), issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
            ssrd_w_m2=42.0, temp2m_c=28.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=80.0, source="test",
        )
    ])

    store2 = RealDataStore(db_path=db_path)
    df = store2.nwp_history_df()
    assert len(df) == 1
    assert df.iloc[0]["ssrd_w_m2"] == 42.0


def test_migrates_pre_candidate_errors_forecast_history_table(tmp_path):
    # Simulates a forecast_history table created before the 2026-07-18
    # candidate_errors column existed (e.g. Railway's persisted
    # NONGFAB_REAL_DATA_DB volume from an older deploy) - opening it with the
    # current RealDataStore must add the column rather than raising "no such
    # column: candidate_errors" on the first record_forecast_points call.
    import sqlite3

    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE forecast_history (
            zone TEXT NOT NULL, horizon TEXT NOT NULL, target_time TEXT NOT NULL, issued_at TEXT NOT NULL,
            pred REAL NOT NULL, lower REAL, upper REAL, algorithm TEXT, error REAL,
            PRIMARY KEY (zone, horizon, target_time)
        );
        """
    )
    conn.commit()
    conn.close()

    store = RealDataStore(db_path=db_path)
    now = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    store.record_forecast_points(
        "GIS", "hour", now,
        [_FakeForecastPoint(timestamp=now, pred=1.0, lower=None, upper=None, algorithm=None, error=None, candidate_errors={"lightgbm": 1.0})],
    )
    rows = store.forecast_history_points("GIS", "hour", since=now)
    assert rows[0][-1] == {"lightgbm": 1.0}


def test_two_in_memory_stores_do_not_share_state():
    store1 = RealDataStore(db_path=":memory:")
    store1.insert_nwp_points([
        _FakeNWPPoint(
            valid_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc), issue_time=datetime(2026, 7, 14, 0, tzinfo=timezone.utc),
            ssrd_w_m2=1.0, temp2m_c=1.0, wind10m_u_ms=1.0, wind10m_v_ms=1.0, relative_humidity_pct=1.0, source="test",
        )
    ])
    store2 = RealDataStore(db_path=":memory:")
    assert store2.counts()["nwp_history"] == 0


@dataclass
class _FakeForecastPoint:
    timestamp: datetime
    pred: float
    lower: float | None
    upper: float | None
    algorithm: str | None
    error: float | None
    candidate_errors: dict[str, float] | None = None


def test_record_and_read_forecast_points_roundtrips():
    store = RealDataStore()
    now = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    points = [
        _FakeForecastPoint(timestamp=now, pred=10.0, lower=8.0, upper=12.0, algorithm="lightgbm", error=1.5),
        _FakeForecastPoint(
            timestamp=now.replace(hour=10), pred=20.0, lower=16.0, upper=24.0, algorithm="lightgbm", error=1.5
        ),
    ]
    inserted = store.record_forecast_points("GIS", "hour", now, points)
    assert inserted == 2

    rows = store.forecast_history_points("GIS", "hour", since=now)
    assert len(rows) == 2
    target_time, pred, lower, upper, algorithm, error, candidate_errors = rows[0]
    assert target_time == now.isoformat()
    assert (pred, lower, upper, algorithm, error) == (10.0, 8.0, 12.0, "lightgbm", 1.5)
    assert candidate_errors == {}


def test_record_forecast_points_roundtrips_candidate_errors():
    store = RealDataStore()
    now = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    point = _FakeForecastPoint(
        timestamp=now, pred=10.0, lower=8.0, upper=12.0, algorithm="lightgbm", error=1.5,
        candidate_errors={"lightgbm": 1.5, "random_forest": 1.8, "sum_k_lstm": 1.6},
    )
    store.record_forecast_points("GIS", "hour", now, [point])

    rows = store.forecast_history_points("GIS", "hour", since=now)
    assert rows[0][-1] == {"lightgbm": 1.5, "random_forest": 1.8, "sum_k_lstm": 1.6}


def test_record_forecast_points_defaults_missing_candidate_errors_attribute():
    # A caller predating the 2026-07-18 candidate_errors field (e.g. a plain
    # object without that attribute) shouldn't raise - getattr(..., None)
    # covers it and the stored/read-back value is just an empty dict.
    class _LegacyPoint:
        timestamp = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
        pred = 5.0
        lower = None
        upper = None
        algorithm = None
        error = None

    store = RealDataStore()
    store.record_forecast_points("GIS", "hour", _LegacyPoint.timestamp, [_LegacyPoint()])
    rows = store.forecast_history_points("GIS", "hour", since=_LegacyPoint.timestamp)
    assert rows[0][-1] == {}


def test_forecast_history_points_excludes_rows_before_since():
    store = RealDataStore()
    now = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    store.record_forecast_points(
        "GIS", "hour", now,
        [_FakeForecastPoint(timestamp=now.replace(hour=h), pred=float(h), lower=None, upper=None, algorithm=None, error=None) for h in (7, 8, 9, 10)],
    )
    rows = store.forecast_history_points("GIS", "hour", since=now)
    assert [r[0] for r in rows] == [now.replace(hour=9).isoformat(), now.replace(hour=10).isoformat()]


def test_record_forecast_points_upserts_on_zone_horizon_target_time():
    # A later issuance for the same (zone, horizon, target_time) overwrites
    # the earlier one - forecasts issued closer to the target hour are more
    # accurate, so the freshest value for a given hour should win.
    store = RealDataStore()
    target = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
    store.record_forecast_points(
        "GIS", "hour", datetime(2026, 7, 18, 6, tzinfo=timezone.utc),
        [_FakeForecastPoint(timestamp=target, pred=10.0, lower=8.0, upper=12.0, algorithm="lightgbm", error=2.0)],
    )
    store.record_forecast_points(
        "GIS", "hour", datetime(2026, 7, 18, 11, tzinfo=timezone.utc),
        [_FakeForecastPoint(timestamp=target, pred=15.0, lower=13.0, upper=17.0, algorithm="random_forest", error=1.0)],
    )
    rows = store.forecast_history_points("GIS", "hour", since=target)
    assert len(rows) == 1
    assert rows[0][1:] == (15.0, 13.0, 17.0, "random_forest", 1.0, {})


def test_forecast_history_points_scoped_to_zone_and_horizon():
    store = RealDataStore()
    now = datetime(2026, 7, 18, 9, tzinfo=timezone.utc)
    store.record_forecast_points("GIS", "hour", now, [_FakeForecastPoint(timestamp=now, pred=1.0, lower=None, upper=None, algorithm=None, error=None)])
    store.record_forecast_points("ISB", "hour", now, [_FakeForecastPoint(timestamp=now, pred=2.0, lower=None, upper=None, algorithm=None, error=None)])
    store.record_forecast_points("GIS", "day", now, [_FakeForecastPoint(timestamp=now, pred=3.0, lower=None, upper=None, algorithm=None, error=None)])

    rows = store.forecast_history_points("GIS", "hour", since=now)
    assert len(rows) == 1
    assert rows[0][1] == 1.0
