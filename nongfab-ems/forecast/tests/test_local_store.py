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
    assert store.counts() == {"nwp_history": 0, "cloud_history": 0, "uv_history": 0}


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
