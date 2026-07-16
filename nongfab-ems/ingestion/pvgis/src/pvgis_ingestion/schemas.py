from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

# Tags every row this module produces, so forecast/local_store.py's nwp_history
# table (shared with nwp_ingestion's real GFS rows) can tell provenance apart -
# and so api/ingestion_scheduler.py can gate this module's own one-time backfill
# on "have we already seeded PVGIS rows specifically", independent of however
# many real GFS rows happen to exist (see that module's own docstring).
SOURCE_NAME = "pvgis-era5"


def _require_tz_aware_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return v.astimezone(timezone.utc)


class PVGISHourlyPoint(BaseModel):
    """One validated PVGIS seriescalc hourly row - real ERA5-reanalysis weather at
    Nong Fab's own coordinates, NOT a forecast (PVGIS has no concept of "issued N
    hours before valid time"). `issue_time` is deliberately set equal to
    `valid_time` for every row this module produces - see backfill.py's own
    docstring for why that's what keeps these rows out of hour-ahead's k-step
    lead-hour buckets (real_data.py's `_nwp_history_with_lead_hours` computes
    lead_hours = valid_time - issue_time, which comes out exactly 0 here, never
    matching any of HOUR_LEAD_HOURS = (1..6)) - Day-ahead training only, a
    deliberate 2026-07-16 scope decision, not an oversight.

    wind10m_v_ms/relative_humidity_pct are unused placeholders, not real PVGIS
    fields - kept only because forecast/local_store.py's nwp_history table schema
    (shared with nwp_ingestion's real GFS rows, which do have real wind/RH) requires
    a value in every column. No current real_data.py builder reads them for either
    source. wind10m_u_ms carries PVGIS's real WS10m (wind speed) with v=0 - PVGIS
    gives no wind *direction*, so there is no real u/v split to report; storing the
    real speed as a directionless "u" axis is a documented simplification, not a
    fabricated direction.
    """

    valid_time: datetime
    issue_time: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    ssrd_w_m2: float = Field(ge=0, le=1500)
    temp2m_c: float = Field(ge=-30, le=60)
    wind10m_u_ms: float = Field(ge=-100, le=100)
    wind10m_v_ms: float = Field(ge=-100, le=100)
    relative_humidity_pct: float = Field(ge=0, le=105)
    source: str = SOURCE_NAME

    @field_validator("issue_time", "valid_time")
    @classmethod
    def _validate_tz_aware(cls, v: datetime) -> datetime:
        return _require_tz_aware_utc(v)


_EXTENSION_BY_CONTENT_TYPE = {"application/json": "json"}


class RawFetchResult(BaseModel):
    """Metadata about a raw JSON payload prior to parsing, used for object-storage
    naming/audit - mirrors ingestion.nasa_power/himawari/nwp's own RawFetchResult.
    """

    url: str
    fetched_at: datetime
    content_type: str
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def object_key(self) -> str:
        ts = self.fetched_at.astimezone(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
        ext = _EXTENSION_BY_CONTENT_TYPE.get(self.content_type, "bin")
        return f"pvgis/{ts}-{self.sha256[:12]}.{ext}"
