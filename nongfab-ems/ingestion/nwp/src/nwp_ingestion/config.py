from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_forecast_hours() -> list[int]:
    # Hourly out to 24h (hour-ahead LightGBM's near-term regressors), then 3-hourly
    # out to 48h (day-ahead NeuralProphet doesn't need finer granularity that far out).
    # Starts at 1, not 0: GFS's f000 (the analysis) has no DSWRF field - downward
    # shortwave radiation is a forecast-accumulated/averaged quantity that only
    # starts existing at f001 - verified live against a real NOMADS GRIB2 file's
    # .idx listing (f000's index has no DSWRF entry at all; f001's has "DSWRF:
    # surface:0-1 hour ave fcst"). Requesting DSWRF at f000 silently gets back
    # whatever else matched the same var/level filter (surface skin temperature)
    # instead, which then fails to decode as sdswrf.
    return list(range(1, 25)) + list(range(27, 49, 3))


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix NWP_)."""

    model_config = SettingsConfigDict(env_prefix="NWP_", env_file=".env", extra="ignore")

    # Nong Fab plant location (approximate) - informational; the actual fetch bbox
    # comes from config/assets.yaml via nongfab_common (see geolocation.py).
    site_latitude: float = 12.71
    site_longitude: float = 101.15

    # Data source selection: "mock" replays the local fixture (safe default for dev/tests),
    # "http" fetches the real NOAA NOMADS GFS filter service. Never defaults to "http" in tests.
    source_mode: str = Field(default="mock", pattern="^(mock|http)$")

    # NOAA NOMADS GFS 0.25deg GRIB filter/subset service - public domain US government
    # data, no credentials required, no robots.txt restriction (verified 404 on
    # nomads.ncep.noaa.gov/robots.txt), officially documented at nomads.ncep.noaa.gov/info.php
    # as the intended way to fetch partial GRIB2 files. See README "Data source & ToS".
    nomads_base_url: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    nomads_prod_dir_template: str = "/gfs.{date:%Y%m%d}/{cycle:02d}/atmos"
    gfs_file_template: str = "gfs.t{cycle:02d}z.pgrb2.0p25.f{fhour:03d}"

    # bbox padding beyond the plant's own bounding box (config/assets.yaml), in degrees.
    # GFS 0.25deg grid spacing is ~27km - this pads enough to guarantee at least one
    # full surrounding grid cell for future spatial interpolation, not just a single point.
    bbox_padding_deg: float = 0.3

    gfs_cycles: list[int] = Field(default_factory=lambda: [0, 6, 12, 18])
    forecast_hours: list[int] = Field(default_factory=_default_forecast_hours)

    # GFS 0.25deg full-res output typically finishes publishing ~3.5-4h after cycle
    # time; padded for margin. lookback_cycles controls how many prior cycles we'll
    # try if the most recent one isn't published yet.
    publish_latency_minutes: int = 240
    lookback_cycles: int = 2

    user_agent: str = "NongFabEMS-NwpIngestion/0.1 (+https://github.com/Drewweiii/solarnwpmos; contact=ops@nongfab-ems.example)"

    request_timeout_seconds: float = 30.0
    # NOMADS's own guidance ("Public Notice of Appropriate Use") is to match request
    # frequency to the data's actual refresh cadence, not to a fixed number - GFS
    # publishes every 6h, so bursts of per-forecast-hour requests within one ingestion
    # cycle are expected; this floor just avoids hammering the CGI script back-to-back.
    min_seconds_between_requests: float = 1.0

    max_retry_attempts: int = 4
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 30.0

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "nwp-raw"

    timescale_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nongfab_ems"

    metrics_port: int = 9102


def get_settings() -> Settings:
    return Settings()
