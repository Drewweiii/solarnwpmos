from pydantic_settings import BaseSettings, SettingsConfigDict


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
