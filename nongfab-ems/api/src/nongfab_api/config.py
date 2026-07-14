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

    # /ws/live push interval
    live_push_interval_seconds: float = 5.0

    port: int = 8000


def get_settings() -> Settings:
    return Settings()
