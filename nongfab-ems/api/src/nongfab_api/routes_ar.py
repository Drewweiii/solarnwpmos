"""GET /ar/{zone}.usdz - AR for iPhone and iPad (2026-07-26, project T).

Project M's WebXR buttons never appear on iOS, because Safari does not implement
WebXR - so every iPhone and iPad in the room got nothing. Apple's route is AR
Quick Look: an `<a rel="ar">` whose href is a `.usdz`, which Safari hands to the
system AR viewer.

TOKEN IN THE QUERY STRING, AND WHY. Quick Look fetches this URL itself, from
outside the page's JavaScript, so there is no way to attach an `Authorization`
header to it. This project already hit the identical constraint with WebSockets
(`ws_chat.py`, `ws_live.py`: "browser WebSocket clients can't set custom
headers") and solved it the same way - `?token=`, decoded with the same
`decode_access_token`, so the endpoint is no less authenticated than any other,
only differently carried. Viewer-level, like the 3D view whose geometry it is.

The model is generated per request rather than cached to disk: it is a few
hundred kilobytes of text, it depends on the zone's current tilt and azimuth
settings, and a stale file on disk would quietly disagree with the 3D view.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response
from nongfab_common.assets import load_assets
from nongfab_features.panel_geometry import generate_zone_layout

from .auth import decode_access_token
from .usdz import PanelPlacement, build_usdz

router = APIRouter(tags=["ar"])

# Apple's registered type for USDZ. Serving it as application/zip makes Safari
# download the file instead of opening AR Quick Look.
USDZ_MEDIA_TYPE = "model/vnd.usdz+zip"


def _require_viewer_from_query(request: Request, token: str) -> None:
    settings = request.app.state.settings
    deploy_id = request.app.state.deploy_id
    user = decode_access_token(token, settings, deploy_id)
    if user.role not in {"viewer", "operator", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="requires role 'viewer' or higher")


@router.get("/ar/{zone}.usdz")
async def get_zone_usdz(
    zone: str,
    request: Request,
    token: str = Query(..., description="Access token; Quick Look cannot send an Authorization header."),
) -> Response:
    _require_viewer_from_query(request, token)

    registry = load_assets()
    known = {z.id for z in registry.zones}
    if zone not in known:
        raise HTTPException(status_code=404, detail=f"unknown zone '{zone}'. known: {sorted(known)}")

    # Same source the 3D view uses, so the AR model and the on-screen scene can
    # never be built from different geometry.
    layout = generate_zone_layout(zone, registry)
    panels = [
        PanelPlacement(
            east_m=p.east_m,
            north_m=p.north_m,
            width_m=p.width_m,
            slant_height_m=p.slant_height_m,
        )
        for p in layout.panels
    ]
    model = build_usdz(panels, layout.tilt_deg, layout.azimuth_deg, zone)

    return Response(
        content=model.data,
        media_type=USDZ_MEDIA_TYPE,
        headers={
            # Quick Look shows this name while loading.
            "Content-Disposition": f'inline; filename="nongfab-{zone}.usdz"',
            "X-Model-Scale": f"{model.scale:.6f}",
            "X-Panel-Count": str(model.panel_count),
        },
    )
