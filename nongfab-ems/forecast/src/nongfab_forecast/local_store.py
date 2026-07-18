"""Lightweight local history store for real ingested weather data (NWP/cloud/UV),
backed by SQLite (stdlib `sqlite3`, no new dependency) - not TimescaleDB.

Why not just use ingestion/nwp and ingestion/himawari's own storage.py: those write
to a *real* Postgres/TimescaleDB via `timescale_dsn` (`pg_insert`'s ON CONFLICT is
Postgres-specific SQL), and the production API (Railway) has no such database
reachable - only an ephemeral local SQLite file for auth, and another for MLflow's
model registry (`mlflow.db`). This store follows that same already-accepted
ephemeral-per-container pattern (see root README's Railway deployment notes) rather
than requiring new infrastructure this session has no credentials to provision.

Each connection is opened per call, not held open across the store's lifetime - the
row counts involved (thousands, not millions) make the reconnect overhead
irrelevant, and it sidesteps sqlite3's cross-thread/cross-asyncio-task connection
sharing pitfalls entirely (see api/'s startup wiring, which calls into this store
from asyncio.to_thread).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nwp_history (
    valid_time TEXT NOT NULL,
    issue_time TEXT NOT NULL,
    ssrd_w_m2 REAL NOT NULL,
    temp2m_c REAL NOT NULL,
    wind10m_u_ms REAL,
    wind10m_v_ms REAL,
    relative_humidity_pct REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (valid_time, issue_time, source)
);
CREATE TABLE IF NOT EXISTS cloud_history (
    observed_at TEXT NOT NULL,
    cloud_opacity_pct REAL NOT NULL,
    cloud_index REAL NOT NULL,
    motion_speed_kmh REAL,
    motion_direction_deg REAL,
    source TEXT NOT NULL,
    PRIMARY KEY (observed_at, source)
);
CREATE TABLE IF NOT EXISTS uv_history (
    observation_date TEXT NOT NULL,
    uv_index REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (observation_date, source)
);
CREATE TABLE IF NOT EXISTS forecast_history (
    zone TEXT NOT NULL,
    horizon TEXT NOT NULL,
    target_time TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    pred REAL NOT NULL,
    lower REAL,
    upper REAL,
    algorithm TEXT,
    error REAL,
    PRIMARY KEY (zone, horizon, target_time)
);
"""


def default_db_path() -> str:
    """`:memory:` unless NONGFAB_REAL_DATA_DB is set - opt-in by design. An
    in-memory default means every unconfigured RealDataStore() (every existing
    test, any ad-hoc script) starts genuinely empty, so real_data.py's
    InsufficientHistoryError path (-> training.py/serving.py's existing synthetic
    fallback) is exercised exactly like before this module existed. Production
    (api/'s lifespan) sets this env var to a real file path so history survives
    across requests within one container's lifetime - see api/README.md.
    """
    return os.environ.get("NONGFAB_REAL_DATA_DB", ":memory:")


class RealDataStore:
    def __init__(self, db_path: str | None = None):
        self._path = db_path if db_path is not None else default_db_path()
        # :memory: needs a single held-open connection (a fresh connect() would be a
        # *different*, independently-empty in-memory DB each time) - every other path
        # reconnects per call, per this module's own docstring.
        self._memory_conn = sqlite3.connect(self._path) if self._path == ":memory:" else None
        if self._memory_conn is not None:
            self._memory_conn.executescript(_SCHEMA)
            self._memory_conn.commit()
        else:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                conn.commit()

    @contextmanager
    def _connect(self):
        if self._memory_conn is not None:
            yield self._memory_conn
            return
        conn = sqlite3.connect(self._path)
        try:
            yield conn
        finally:
            conn.close()

    def insert_nwp_points(self, points: Iterable) -> int:
        """`points` are nwp_ingestion.schemas.NWPForecastPoint (or anything with the
        same attributes) - upserts on (valid_time, issue_time, source), so re-ingesting
        an already-seen cycle is idempotent.
        """
        rows = [
            (
                p.valid_time.isoformat(), p.issue_time.isoformat(), float(p.ssrd_w_m2), float(p.temp2m_c),
                float(p.wind10m_u_ms), float(p.wind10m_v_ms), float(p.relative_humidity_pct), p.source,
            )
            for p in points
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO nwp_history "
                "(valid_time, issue_time, ssrd_w_m2, temp2m_c, wind10m_u_ms, wind10m_v_ms, relative_humidity_pct, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def insert_cloud_frames(self, frames: Iterable) -> int:
        """`frames` are himawari_ingestion.schemas.CloudRasterFrame (or anything with
        observed_at/nong_fab_cloud_opacity_pct/nong_fab_cloud_index/source, optionally
        motion_speed_kmh/motion_direction_deg). Motion fields use getattr(..., None)
        rather than a hard attribute requirement: CloudRasterFrame's own fields are
        null on a run's first frame (no previous frame to diff against yet - see that
        class's docstring), and older/simpler test doubles may not carry them at all.
        """
        rows = [
            (
                f.observed_at.isoformat(), float(f.nong_fab_cloud_opacity_pct), float(f.nong_fab_cloud_index),
                getattr(f, "motion_speed_kmh", None), getattr(f, "motion_direction_deg", None), f.source,
            )
            for f in frames
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO cloud_history "
                "(observed_at, cloud_opacity_pct, cloud_index, motion_speed_kmh, motion_direction_deg, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def insert_uv_observations(self, observations: Iterable) -> int:
        rows = [(o.observation_date.isoformat(), float(o.uv_index), o.source) for o in observations]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO uv_history (observation_date, uv_index, source) VALUES (?, ?, ?)", rows
            )
            conn.commit()
        return len(rows)

    def nwp_history_df(self) -> pd.DataFrame:
        with self._connect() as conn:
            df = pd.read_sql_query("SELECT * FROM nwp_history ORDER BY valid_time", conn)
        if len(df):
            df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
            df["issue_time"] = pd.to_datetime(df["issue_time"], utc=True)
        return df

    def cloud_history_df(self) -> pd.DataFrame:
        with self._connect() as conn:
            df = pd.read_sql_query("SELECT * FROM cloud_history ORDER BY observed_at", conn)
        if len(df):
            df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
        return df

    def uv_history_df(self) -> pd.DataFrame:
        with self._connect() as conn:
            df = pd.read_sql_query("SELECT * FROM uv_history ORDER BY observation_date", conn)
        if len(df):
            df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
        return df

    def latest_cloud_observation(self) -> tuple[datetime, float, float] | None:
        """(observed_at, cloud_opacity_pct, cloud_index) of the single most recent
        row, or None if empty - used by real_data.physics_baseline_series() to decide
        whether recent-enough live cloud data exists to attenuate the clear-sky curve.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT observed_at, cloud_opacity_pct, cloud_index FROM cloud_history ORDER BY observed_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0]), row[1], row[2]

    def record_forecast_points(self, zone: str, horizon: str, issued_at: datetime, points: Iterable) -> int:
        """Upserts each point keyed by (zone, horizon, target_time) - `points`
        are serving.ForecastPoint (or anything with the same
        timestamp/pred/lower/upper/algorithm/error attributes). A later call
        for the same target hour overwrites the earlier one: a forecast
        issued closer to its target time is more accurate, so the freshest
        issuance for a given hour should be what gets served back.

        This is what makes `/forecast` able to keep showing a real
        prediction for an hour that has since passed (the Forecast line and
        Prediction interval band used to visibly vanish the moment an hour
        dropped out of `serving.py`'s forward-only computed window - the
        user's own 2026-07-18 report) without relying on the frontend having
        stayed open across every poll to remember it - see
        `forecast_history_points()` below, which is what actually serves the
        merged past+future window back.
        """
        rows = [
            (zone, horizon, p.timestamp.isoformat(), issued_at.isoformat(), float(p.pred), p.lower, p.upper, p.algorithm, p.error)
            for p in points
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO forecast_history "
                "(zone, horizon, target_time, issued_at, pred, lower, upper, algorithm, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)

    def forecast_history_points(self, zone: str, horizon: str, since: datetime) -> list[tuple]:
        """Rows `(target_time, pred, lower, upper, algorithm, error)` for one
        zone/horizon, `target_time >= since`, oldest first - the persisted
        counterpart to whatever `serving.py` just computed fresh, so a caller
        can merge "what's recorded" (which may include hours now in the
        past) with "what was just predicted forward" into one series. Bounded
        by `since` rather than returned in full, so a long-running deployment
        doesn't grow the response by however many days it's been up.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT target_time, pred, lower, upper, algorithm, error FROM forecast_history "
                "WHERE zone = ? AND horizon = ? AND target_time >= ? ORDER BY target_time",
                (zone, horizon, since.isoformat()),
            ).fetchall()
        return rows

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 - table names are this module's own constants, never user input
                for table in ("nwp_history", "cloud_history", "uv_history", "forecast_history")
            }

    def count_nwp_rows_by_source(self, source: str) -> int:
        """Row count for one `source` tag within nwp_history - unlike counts()'s
        per-table totals, this lets a caller gate a specific source's own one-time
        backfill (e.g. pvgis_ingestion's) independently of however many rows a
        *different* source (e.g. nwp_ingestion's live GFS poll) has already
        contributed to the same shared table - see api/ingestion_scheduler.py's
        _backfill_pvgis.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM nwp_history WHERE source = ?", (source,)).fetchone()
        return row[0]


__all__ = ["RealDataStore", "default_db_path"]
