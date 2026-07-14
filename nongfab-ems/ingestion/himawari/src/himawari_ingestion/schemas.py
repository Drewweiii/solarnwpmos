from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


def _require_tz_aware_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return v.astimezone(timezone.utc)


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
    def _validate_observed_at(cls, v: datetime) -> datetime:
        return _require_tz_aware_utc(v)


_EXTENSION_BY_CONTENT_TYPE = {
    "application/json": "json",
    "application/octet-stream": "npz",  # raster frames (numpy .npz payload)
}


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
        ext = _EXTENSION_BY_CONTENT_TYPE.get(self.content_type, "bin")
        return f"himawari/{ts}-{self.sha256[:12]}.{ext}"


class CloudRasterFrame(BaseModel):
    """Metadata for one tile snapshot (the pixel arrays themselves live in MinIO as an
    .npz - see datasource.py). Bounding box covers all 3 Nong Fab zones plus a
    wind-drift buffer so the minute-ahead CNN-LSTM can see a cloud front approaching
    before it reaches the site (see geolocation.NONG_FAB_BBOX for the calibration).

    nong_fab_cloud_opacity_pct / nong_fab_cloud_index are the value sampled at the
    plant's own coordinate from within this same tile (no extra fetch) - kept for
    simple consumers that just want a single time series (see CloudObservation).
    motion_* fields are null on the first frame of a run (no previous frame to diff
    against yet) or whenever consecutive frames have mismatched shapes.
    """

    observed_at: datetime
    source: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    rows: int = Field(gt=0)
    cols: int = Field(gt=0)
    nong_fab_cloud_opacity_pct: float = Field(ge=0, le=100)
    nong_fab_cloud_index: float = Field(ge=-0.2, le=1.5)
    motion_speed_kmh: float | None = None
    motion_direction_deg: float | None = Field(default=None, ge=0, le=360)

    @field_validator("observed_at")
    @classmethod
    def _validate_observed_at(cls, v: datetime) -> datetime:
        return _require_tz_aware_utc(v)
