from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars or .env (prefix PVGIS_)."""

    model_config = SettingsConfigDict(env_prefix="PVGIS_", env_file=".env", extra="ignore")

    # Matches config/assets.yaml's site.nominal_center (see nongfab_features.clearsky.
    # nong_fab_site_location's own docstring: "the single source of truth other
    # modules should use too") - same literal-default convention as
    # nasa_power_ingestion.config.Settings, not a dynamic load_assets() call at
    # class-definition time.
    site_latitude: float = 12.71
    site_longitude: float = 101.15

    # Data source selection: "mock" replays the local fixture (safe default for dev/
    # tests), "http" fetches the real PVGIS seriescalc API. Never defaults to "http"
    # in tests.
    source_mode: str = Field(default="mock", pattern="^(mock|http)$")

    # PVGIS (Photovoltaic Geographical Information System), European Commission
    # Joint Research Centre - public, free, no API key/registration required (see
    # README "Data source & ToS"). seriescalc returns a full year of hourly
    # ERA5-reanalysis-based irradiance/temperature for a single point - real
    # historical weather for Nong Fab's own coordinates, not a forecast (see
    # backfill.py's own docstring for why this only feeds Day-ahead, never
    # Intra-day's k-step lead-hour buckets).
    base_url: str = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"

    # A single, specific, already-fully-published year (PVGIS-ERA5 has no "latest
    # year" alias) - live-verified reachable and returning real data for this exact
    # year via Railway's own console 2026-07-16 (see README), not guessed from docs.
    year: int = 2020

    # Echoed to the API to shape the "P"/pvcalculation fields this module doesn't
    # use (see datasource.py's own docstring on why G(i)/T2m are read instead) -
    # PVGIS's own stated default, not tuned.
    system_loss_pct: float = 14.0
    reference_peak_power_kwp: float = 1.0

    # A full year of hourly JSON is a bigger single payload than this repo's other
    # ingestion modules' typical calls (~8760-8784 rows) - longer timeout than
    # nasa_power_ingestion's default.
    request_timeout_seconds: float = 60.0

    max_retry_attempts: int = 4
    retry_backoff_base_seconds: float = 2.0
    retry_backoff_max_seconds: float = 30.0

    user_agent: str = "NongFabEMS-PvgisIngestion/0.1 (+https://github.com/Drewweiii/solarnwpmos; contact=ops@nongfab-ems.example)"


def get_settings() -> Settings:
    return Settings()
