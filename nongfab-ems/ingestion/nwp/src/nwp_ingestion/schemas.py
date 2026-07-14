from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


def _require_tz_aware_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return v.astimezone(timezone.utc)


class NWPForecastPoint(BaseModel):
    """One validated GFS forecast value at a single grid point, for a single
    (issue_time, valid_time) pair. GFS's own variable names (DSWRF/TMP/UGRD/VGRD/RH)
    are kept in spirit but normalized to physical units the rest of the pipeline
    expects (Celsius, not Kelvin; ssrd_w_m2 mirrors the paper's "SSRD" terminology,
    even though GFS's own GRIB short_name is sdswrf, not ssrd - ECMWF/CDS naming).
    """

    issue_time: datetime  # GFS cycle run time (00/06/12/18 UTC)
    valid_time: datetime  # forecast-valid time = issue_time + lead time
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    ssrd_w_m2: float = Field(ge=0, le=1500)  # surface downward shortwave radiation flux
    temp2m_c: float = Field(ge=-30, le=60)
    wind10m_u_ms: float = Field(ge=-100, le=100)
    wind10m_v_ms: float = Field(ge=-100, le=100)
    relative_humidity_pct: float = Field(ge=0, le=105)  # GFS RH can slightly exceed 100 (model artifact)
    source: str

    @field_validator("issue_time", "valid_time")
    @classmethod
    def _validate_tz_aware(cls, v: datetime) -> datetime:
        return _require_tz_aware_utc(v)


_EXTENSION_BY_CONTENT_TYPE = {
    "application/x-grib2": "grib2",
}


class RawFetchResult(BaseModel):
    """Metadata about a raw GRIB2 payload prior to decoding, used for MinIO object
    naming/audit - mirrors ingestion.himawari's RawFetchResult.
    """

    url: str
    fetched_at: datetime
    content_type: str
    body: bytes
    issue_time: datetime
    forecast_hour: int = Field(ge=0)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def object_key(self) -> str:
        issue = self.issue_time.astimezone(timezone.utc)
        ext = _EXTENSION_BY_CONTENT_TYPE.get(self.content_type, "bin")
        return f"nwp/{issue:%Y/%m/%d/%H}/f{self.forecast_hour:03d}-{self.sha256[:12]}.{ext}"
