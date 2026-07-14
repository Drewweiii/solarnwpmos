"""GET /assets, GET /assets/{zone_id} - plant geometry/equipment registry
(config/assets.yaml via nongfab_common.assets.load_assets()), the same
source of truth every other module reads from.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from nongfab_common.assets import AssetRegistry, Zone, load_assets

from .auth import require_role

router = APIRouter(tags=["assets"])


@router.get("/assets", response_model=AssetRegistry)
async def get_assets(_user=Depends(require_role("viewer"))) -> AssetRegistry:
    return load_assets()


@router.get("/assets/{zone_id}", response_model=Zone)
async def get_zone(zone_id: str, _user=Depends(require_role("viewer"))) -> Zone:
    registry = load_assets()
    try:
        return registry.zone(zone_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
