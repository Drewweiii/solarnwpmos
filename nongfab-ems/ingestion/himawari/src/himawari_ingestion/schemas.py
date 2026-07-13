from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class CloudObservation(BaseModel):
    """A single validated cloud-opacity/cloud-index reading at a point in time.

    Range bounds reflect the published Himawari cloud-product conventions:
    opacity is a 0-100% coverage estimate; cloud index is a normalized clear-sky
    departure that can slightly exceed [0, 1] under snow/sun-glint artifacts,
    hence the padded [-0.2, 1.5] band rather than a strict unit interval.
    """

    observed_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    cloud_opacity_pct: float = Field(ge=0, le=100)
    cloud_index: float = Field(ge=-0.2, le=1.5)
    source: str

    @field_validator("observed_at")
    @classmethod
    def _require_tz_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return v.astimezone(timezone.utc)


class RawFetchResult(BaseModel):
    """Metadata about a raw payload prior to parsing, used for MinIO object naming/audit."""

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
        return f"himawari/{ts}-{self.sha256[:12]}.bin"
