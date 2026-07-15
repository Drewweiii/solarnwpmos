from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix NASA_POWER_)."""

    model_config = SettingsConfigDict(env_prefix="NASA_POWER_", env_file=".env", extra="ignore")

    site_latitude: float = 12.71
    site_longitude: float = 101.15

    # Data source selection: "mock" replays the local fixture (safe default for dev/tests),
    # "http" fetches the real NASA POWER daily point API. Never defaults to "http" in tests.
    source_mode: str = Field(default="mock", pattern="^(mock|http)$")

    # NASA POWER (Prediction Of Worldwide Energy Resources) daily point API - public,
    # free, no API key/registration required (see README "Data source & ToS"). Chosen
    # over the GFS/Himawari feeds for UV specifically because neither publishes a UV
    # index field; NASA POWER's ALLSKY_SFC_UV_INDEX is a stable, documented product.
    base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    community: str = "RE"  # "Renewable Energy" community preset - the parameter set this module needs
    parameters: str = "ALLSKY_SFC_UV_INDEX"

    # NASA POWER is a daily-aggregate product (not hourly/real-time) with a
    # multi-day publication lag for the most recent dates - unlike Himawari/GFS,
    # there is no "poll every N minutes" mode here, just a periodic daily refresh
    # (the caller - forecast/'s real-data feature layer - decides its own cadence;
    # this module has no scheduler.py of its own, see README "Scope").
    publish_latency_days: int = 3

    backfill_lookback_days: int = 30

    # NASA POWER's own documented missing-data sentinel (not a validation range this
    # module invented) - see README "Data source & ToS".
    missing_value_sentinel: float = -999.0

    user_agent: str = "NongFabEMS-NasaPowerIngestion/0.1 (+https://github.com/Drewweiii/solarnwpmos; contact=ops@nongfab-ems.example)"

    request_timeout_seconds: float = 30.0
    min_seconds_between_requests: float = 1.0

    max_retry_attempts: int = 4
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 30.0


def get_settings() -> Settings:
    return Settings()
