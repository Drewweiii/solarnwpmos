from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_nwp_poll_forecast_hours() -> list[int]:
    # Hourly to 24h (hour-ahead's k-step models + day-ahead's near-term
    # regressors need this density), 3-hourly 27-48h, 6-hourly 54-72h (day-ahead's
    # far end doesn't need finer than this) - reaches the full 72h/3-day day-ahead
    # horizon (see forecast/serving.py's MAX_DAY_AHEAD_HOURS) while staying lighter
    # than nwp_ingestion.config.Settings' own default (this runs every poll tick
    # in-process, not as a separate scheduled job).
    return list(range(1, 25)) + list(range(27, 49, 3)) + list(range(54, 73, 6))


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix API_)."""

    model_config = SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore")

    timescale_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems"

    # JWT signing - dev-only default secret, NEVER used as-is in production (see
    # README "Auth" section). Real deployments must override via API_JWT_SECRET_KEY.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Seeds a small set of demo accounts (admin/operator/viewer) into the users
    # table on startup if it's empty - dev/demo convenience only, see README.
    seed_demo_users: bool = True

    # Create the ORM tables (the `users` table - models.Base) on startup if
    # they don't already exist. On the docker-compose Postgres path the
    # db/migrations SQL is the source of truth and this is a harmless
    # idempotent no-op (checkfirst); it exists so a zero-setup deployment
    # (e.g. an ephemeral SQLite auth store for a public demo, where running a
    # separate migration step isn't worth it) still has its auth table.
    create_tables_on_startup: bool = True

    # /ws/live push interval
    live_push_interval_seconds: float = 5.0

    # Real-data background ingestion (ingestion_scheduler.py) - runs inside this
    # API process rather than as separate deployed services, since this
    # deployment has no persistent TimescaleDB for ingestion/nwp's and
    # ingestion/himawari's own storage.py to write to (see root README "Known
    # gaps" and forecast/local_store.py's docstring). Defaults ON so a fresh
    # deploy actually produces real forecasts without a manual step; the
    # `settings` test fixture (api/tests/conftest.py) explicitly disables it so
    # the test suite stays hermetic/fast, matching how live_push_interval_seconds
    # is already overridden there.
    enable_background_ingestion: bool = True
    real_data_db_path: str = ""  # empty -> forecast.local_store.RealDataStore's own default (:memory:, single app-lifetime instance)
    backfill_lookback_days: int = 30
    himawari_poll_interval_seconds: float = 600.0  # 10 min, matches Himawari's native product cadence
    nwp_poll_interval_seconds: float = 3600.0  # 1h - GFS only publishes every 6h, hourly is already generous
    nwp_poll_forecast_hours: list[int] = Field(default_factory=_default_nwp_poll_forecast_hours)
    # Adaptive retrain cadence (ingestion_scheduler._retrain_forever): frequent
    # while real history is still thin (each new poll tick meaningfully changes
    # a small training set - most valuable to retrain on quickly), then spaced
    # out once enough real history has accumulated that one more poll tick's
    # worth of data barely moves the model (diminishing returns) - per Songsiri
    # reference deck's own framing that a forecast's skill is bounded by how
    # much real history trained it, not by how often you retrain past that
    # point. Regime picked each cycle from the live nwp_history row count
    # (RealDataStore.counts()), not a one-time startup decision, so a
    # deployment that starts cold and accumulates real data over time
    # transitions automatically without a restart.
    retrain_interval_cold_seconds: float = 3600.0  # 1h
    retrain_interval_warm_seconds: float = 21600.0  # 6h - one retrain per real GFS cycle
    retrain_warm_threshold_rows: int = 500  # nwp_history row count at/above which the "cold" thin-history period is considered over

    port: int = 8000

    # Browser origins allowed to call this API cross-origin (the dashboard in
    # web/ runs on its own Vite dev server port, or its own domain in prod -
    # always a different origin than this API). Comma-separated; kept as a
    # plain str field (not list[str]) since pydantic-settings otherwise
    # expects list-typed env vars to be JSON, not a plain comma list. Override
    # via API_CORS_ORIGINS for a real deployment's dashboard origin(s).
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_allow_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    return Settings()
