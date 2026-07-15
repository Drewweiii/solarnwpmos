from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field, field_validator


class UVObservation(BaseModel):
    """One validated daily UV index reading at a single point - NASA POWER is a daily
    (not sub-daily) product, so there's no observed_at time-of-day, only a date.
    """

    observation_date: date
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    uv_index: float = Field(ge=0, le=25)  # WHO UV Index scale tops out around 11+ in practice; 25 is a generous ceiling
    source: str

    @field_validator("uv_index")
    @classmethod
    def _reject_missing_sentinel(cls, v: float) -> float:
        if v <= -900:
            raise ValueError("uv_index is NASA POWER's missing-data sentinel (~-999), not a real reading")
        return v


_EXTENSION_BY_CONTENT_TYPE = {"application/json": "json"}


class RawFetchResult(BaseModel):
    """Metadata about a raw JSON payload prior to parsing, used for object-storage
    naming/audit - mirrors ingestion.himawari/nwp's own RawFetchResult.
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
        return f"nasa-power/{ts}-{self.sha256[:12]}.{ext}"
