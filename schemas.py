"""
backend/app/schemas/forecast.py
Pydantic v2 schemas for API communication.
"""
from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HorizonType(str, enum.Enum):
    minute_ahead = "minute_ahead"
    hour_ahead = "hour_ahead"
    day_ahead = "day_ahead"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    site_code: str = Field(..., examples=["ISB", "GIS"])
    horizon_type: HorizonType = Field(..., description="Router selects the model from this.")
    issued_at: datetime | None = Field(None, description="Defaults to now (UTC).")
    steps: int | None = Field(None, ge=1, le=168, description="Override number of lead steps.")
    pi_nominal: float = Field(0.80, ge=0.5, le=0.99, description="Prediction-interval coverage.")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
class ForecastPoint(BaseModel):
    target_time: datetime
    lead_minutes: int
    p_hat_kw: float
    p_lower_kw: float | None = None
    p_upper_kw: float | None = None


class ReserveSignal(BaseModel):
    """Derived operational signals for GTG dispatch."""
    spinning_reserve_kw: float = Field(..., description="max(0, p_hat - p_lower) over horizon")
    max_ramp_down_kw_per_min: float = Field(..., description="Steepest expected solar drop")
    ramp_warning: bool = Field(..., description="True if drop exceeds GTG ramp capability")
    zero_export_risk: bool = Field(False, description="Solar may exceed net plant load")


class ForecastResponse(BaseModel):
    site_code: str
    horizon_type: HorizonType
    model_name: str
    generated_at: datetime
    pi_nominal: float
    points: list[ForecastPoint]
    reserve: ReserveSignal


# ---------------------------------------------------------------------------
# Ingestion (ETL → API)
# ---------------------------------------------------------------------------
class TelemetryIn(BaseModel):
    time: datetime
    site_code: str
    p_ac_kw: float
    irradiance_wm2: float | None = None
    module_temp_c: float | None = None
    inverter_ok: bool = True


class WeatherIn(BaseModel):
    valid_time: datetime
    issued_at: datetime
    source: str
    ssrd_wm2: float | None = None
    temp_c: float | None = None
    wind_ms: float | None = None
    rh_pct: float | None = None
    cloud_index: float | None = None
    cloud_opacity: float | None = None
