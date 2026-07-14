from __future__ import annotations

from dataclasses import dataclass

from nongfab_common.assets import load_assets
from nongfab_common.assets import target_bbox as _config_target_bbox


@dataclass(frozen=True)
class FetchBBox:
    """The lat/lon window requested from the GFS filter service - the plant's own
    bounding box (config/assets.yaml) padded further, since GFS's 0.25deg grid is
    much coarser than Himawari's - padding guarantees at least one full surrounding
    grid cell rather than a single interpolated point.
    """

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


def nong_fab_fetch_bbox(padding_deg: float = 0.3) -> FetchBBox:
    registry = load_assets()
    lat_min, lat_max, lon_min, lon_max = _config_target_bbox(registry)
    return FetchBBox(
        lat_min=lat_min - padding_deg,
        lat_max=lat_max + padding_deg,
        lon_min=lon_min - padding_deg,
        lon_max=lon_max + padding_deg,
    )
