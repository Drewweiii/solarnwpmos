from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix HIMAWARI_)."""

    model_config = SettingsConfigDict(env_prefix="HIMAWARI_", env_file=".env", extra="ignore")

    # Nong Fab plant location (approximate) - used for both the calibrated pixel lookup
    # and sanity-checking that observations returned by the data source are plausible.
    site_latitude: float = 12.71
    site_longitude: float = 101.15

    # Data source selection: "mock" replays the local fixture (safe default for dev/tests),
    # "http" reads the real NOAA AHI cloud product. Never defaults to "http" in tests.
    source_mode: str = Field(default="mock", pattern="^(mock|http)$")

    # NOAA/NESDIS AHI-L2-FLDK-Clouds product on AWS Open Data (s3://noaa-himawari9),
    # public domain US government data, no credentials required. See README "Data source".
    noaa_bucket: str = "noaa-himawari9"
    noaa_product_prefix: str = "AHI-L2-FLDK-Clouds"
    noaa_file_prefix: str = "AHI-CMSK"  # Cloud Mask product within that prefix
    publish_latency_minutes: int = 55  # observed ~40min NOAA processing lag; padded for margin
    lookback_slots: int = 6  # how many 10-min slots to search backward for a published file

    user_agent: str = "NongFabEMS-HimawariIngestion/0.2 (+https://github.com/Drewweiii/solarnwpmos; contact=ops@nongfab-ems.example)"

    request_timeout_seconds: float = 30.0
    min_seconds_between_requests: float = 2.0  # applies to the S3 list-objects calls

    # tenacity retry policy (applied to the pixel-read step)
    max_retry_attempts: int = 4
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 30.0

    poll_interval_minutes: int = 10

    # Historical backfill (backfill.py) - seeds cold-start training history instead
    # of waiting for live polling to accumulate it. Native 10-min cadence over 30
    # days would be 4320 fetches (each a list-objects + a range-read), too many for
    # a one-shot boot-time job - backfill_cadence_minutes samples coarser than
    # poll_interval_minutes on purpose; see backfill.py's own docstring.
    backfill_lookback_days: int = 30
    backfill_cadence_minutes: int = 60

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "himawari-raw"

    timescale_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems"

    metrics_port: int = 9101


def get_settings() -> Settings:
    return Settings()
