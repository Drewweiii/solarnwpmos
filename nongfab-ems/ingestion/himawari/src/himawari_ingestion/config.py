from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix HIMAWARI_)."""

    model_config = SettingsConfigDict(env_prefix="HIMAWARI_", env_file=".env", extra="ignore")

    # Nong Fab plant location (approximate) - used for both the API query point and
    # sanity-checking that observations returned by the data source are plausible.
    site_latitude: float = 12.71
    site_longitude: float = 101.15

    # Data source selection: "mock" replays the local fixture (safe default for dev/tests),
    # "http" calls the real endpoint below. Never defaults to "http" in tests.
    source_mode: str = Field(default="mock", pattern="^(mock|http)$")

    base_url: str = "https://himawari.optemis.space"
    api_path: str = "/api/v1/latest"  # placeholder: unverified pending live site access, see README
    user_agent: str = "NongFabEMS-HimawariIngestion/0.1 (+https://github.com/Drewweiii/solarnwpmos; contact=ops@nongfab-ems.example)"

    request_timeout_seconds: float = 15.0
    min_seconds_between_requests: float = 5.0  # rate limit floor, independent of the schedule interval

    # tenacity retry policy
    max_retry_attempts: int = 4
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 30.0

    # Compliance gate: if robots.txt cannot be fetched/parsed, fail closed unless explicitly overridden.
    allow_fetch_if_robots_unreachable: bool = False
    robots_cache_ttl_seconds: float = 3600.0

    poll_interval_minutes: int = 10

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "himawari-raw"

    timescale_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems"

    metrics_port: int = 9101


def get_settings() -> Settings:
    return Settings()
