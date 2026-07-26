"""Write a USDZ of the array, so iPhones and iPads get AR too (2026-07-26, project T).

Project M gave the 3D view WebXR AR/VR. iOS Safari does not implement WebXR and
shows no button there at all, which is honest but leaves out every iPhone and
iPad in the room. Apple's own path is **AR Quick Look**: an `<a rel="ar">`
pointing at a `.usdz`, which Safari opens in the system AR viewer. Same feature,
completely different plumbing.

NO NEW DEPENDENCY. A USDZ is not a special binary - it is an uncompressed ZIP
containing a USD layer, and USD has a plain-text form (`.usda`). Both are
written here in about a hundred lines rather than pulling in `usd-core`, which
is a 30 MB wheel that this service would carry on every deploy to emit one
static-shaped file. The one real constraint the format adds is alignment: every
entry's *data* must begin on a 64-byte boundary so the viewer can memory-map it,
which `_aligned_zip` handles by padding each local header's extra field.

WHAT IS IN THE MODEL, AND AT WHAT SCALE. Real surveyed panel positions and
sizes, the zone's tilt and azimuth as the API reports them, merged into a single
mesh - 600 separate prims would be a needlessly large file for 600 identical
rectangles. The array spans hundreds of metres, so the model is scaled to sit on
a table; the scale factor is returned to the caller so the UI can print it,
which is the same rule project M set for WebXR: an AR model with no stated scale
invites reading its size as the real one.
"""

from __future__ import annotations

import io
import math
import struct
import zipfile
from dataclasses import dataclass

# USDZ requires every file's payload to start 64-byte aligned.
_USDZ_ALIGNMENT = 64
# A ZIP extra field cannot be 1-3 bytes: it needs a 2-byte id and a 2-byte
# length before any payload.
_MIN_EXTRA = 4
# Arbitrary, unregistered extra-field id used purely as padding. Readers skip
# unknown ids, which is exactly what we want.
_PAD_FIELD_ID = 0x1986

TABLETOP_SPAN_M = 0.6
"""Target size of the whole array once it lands on a table, in metres. Matches
`web/src/lib/xr.ts`'s constant of the same name so the WebXR and Quick Look
paths put the model at the same size."""

PANEL_CLEARANCE_M = 0.8
"""Height of the panels' lower edge above ground in the model. A mounting height
was never surveyed (see `zone.*.tilt_deg`'s registry note - the angles are not
measured either), so this is a plausible constant chosen to keep the array off
the floor, not a site figure. It affects nothing but how the model looks."""


@dataclass(frozen=True)
class PanelPlacement:
    east_m: float
    north_m: float
    width_m: float
    slant_height_m: float


@dataclass(frozen=True)
class UsdzModel:
    data: bytes
    scale: float
    panel_count: int

    def scale_ratio_label(self) -> str:
        """"1 : 250", for printing next to the AR button."""
        if self.scale >= 1:
            return "1 : 1"
        return f"1 : {round(1 / self.scale)}"


def _panel_corners(
    panel: PanelPlacement, tilt_deg: float, azimuth_deg: float
) -> list[tuple[float, float, float]]:
    """The four corners of one panel in metres, Y up, X east, Z north.

    Azimuth is measured from north towards east, which is the convention the
    rest of this project uses; the panel faces that way and slopes down towards
    it by `tilt_deg`.
    """
    az = math.radians(azimuth_deg)
    tilt = math.radians(tilt_deg)

    # Across the panel, horizontal, perpendicular to the direction it faces.
    wx, wy, wz = math.cos(az), 0.0, -math.sin(az)
    # Down the slope, towards the facing direction, dropping by the tilt.
    sx = math.sin(az) * math.cos(tilt)
    sy = -math.sin(tilt)
    sz = math.cos(az) * math.cos(tilt)

    hw = panel.width_m / 2
    hs = panel.slant_height_m / 2
    # Lift the centre so the low edge clears the ground rather than sinking
    # through it once the panel is tilted.
    cy = PANEL_CLEARANCE_M + abs(hs * math.sin(tilt))
    cx, cz = panel.east_m, panel.north_m

    corners = []
    for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        corners.append(
            (
                cx + wx * hw * du + sx * hs * dv,
                cy + wy * hw * du + sy * hs * dv,
                cz + wz * hw * du + sz * hs * dv,
            )
        )
    return corners


def _fmt(value: float) -> str:
    # Three decimals is well under a millimetre at model scale and keeps the
    # layer text a third of the size a full repr would.
    return f"{value:.3f}"


def _doc(zone: str, scale: float) -> str:
    """The `doc` metadata AR Quick Look surfaces in its share sheet - the only
    place the model itself can state its own scale and provenance."""
    return (
        f"PTT LNG Terminal 2 (Nong Fab) solar array, zone {zone}. "
        "Panel positions and sizes are surveyed. Tilt and azimuth are as the "
        "site asset registry reports them. "
        f"Scaled to {_fmt(scale)} of real size for tabletop AR."
    )


def build_usda(
    panels: list[PanelPlacement],
    tilt_deg: float,
    azimuth_deg: float,
    zone: str,
    scale: float,
) -> str:
    """One merged mesh of every panel, plus a ground pad, as USD ASCII."""
    points: list[tuple[float, float, float]] = []
    counts: list[int] = []
    indices: list[int] = []
    for panel in panels:
        base = len(points)
        points.extend(_panel_corners(panel, tilt_deg, azimuth_deg))
        counts.append(4)
        indices.extend([base, base + 1, base + 2, base + 3])

    if points:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        extent = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
        pad_half = max(max(xs) - min(xs), max(zs) - min(zs)) / 2 + 4
        pad_cx = (max(xs) + min(xs)) / 2
        pad_cz = (max(zs) + min(zs)) / 2
    else:
        extent = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        pad_half, pad_cx, pad_cz = 1.0, 0.0, 0.0

    pts = ", ".join(f"({_fmt(x)}, {_fmt(y)}, {_fmt(z)})" for x, y, z in points)
    ext = ", ".join(f"({_fmt(a)}, {_fmt(b)}, {_fmt(c)})" for a, b, c in extent)

    ground_pts = ", ".join(
        f"({_fmt(pad_cx + dx * pad_half)}, 0, {_fmt(pad_cz + dz * pad_half)})"
        for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )

    return f"""#usda 1.0
(
    defaultPrim = "NongFab"
    metersPerUnit = 1
    upAxis = "Y"
    doc = "{_doc(zone, scale)}"
)

def Xform "NongFab" (
    kind = "component"
)
{{
    double3 xformOp:scale = ({scale}, {scale}, {scale})
    uniform token[] xformOpOrder = ["xformOp:scale"]

    def Scope "Looks"
    {{
        def Material "PanelMaterial"
        {{
            token outputs:surface.connect = </NongFab/Looks/PanelMaterial/Surface.outputs:surface>

            def Shader "Surface"
            {{
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = (0.055, 0.094, 0.22)
                float inputs:metallic = 0.35
                float inputs:roughness = 0.28
                token outputs:surface
            }}
        }}

        def Material "GroundMaterial"
        {{
            token outputs:surface.connect = </NongFab/Looks/GroundMaterial/Surface.outputs:surface>

            def Shader "Surface"
            {{
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = (0.44, 0.43, 0.40)
                float inputs:metallic = 0
                float inputs:roughness = 0.95
                token outputs:surface
            }}
        }}
    }}

    def Mesh "Ground"
    {{
        float3[] extent = [({_fmt(pad_cx - pad_half)}, 0, {_fmt(pad_cz - pad_half)}), ({_fmt(pad_cx + pad_half)}, 0, {_fmt(pad_cz + pad_half)})]
        int[] faceVertexCounts = [4]
        int[] faceVertexIndices = [0, 1, 2, 3]
        point3f[] points = [{ground_pts}]
        uniform token subdivisionScheme = "none"
        rel material:binding = </NongFab/Looks/GroundMaterial>
    }}

    def Mesh "Panels"
    {{
        float3[] extent = [{ext}]
        int[] faceVertexCounts = [{", ".join(str(c) for c in counts)}]
        int[] faceVertexIndices = [{", ".join(str(i) for i in indices)}]
        point3f[] points = [{pts}]
        uniform token subdivisionScheme = "none"
        rel material:binding = </NongFab/Looks/PanelMaterial>
    }}
}}
"""


def _aligned_zip(files: list[tuple[str, bytes]]) -> bytes:
    """A USDZ package: stored (never deflated), every payload 64-byte aligned.

    The alignment is not decoration - AR Quick Look memory-maps the archive, and
    a misaligned layer is rejected rather than rendered badly, which would look
    from the outside like "AR just does not work on this phone".
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, payload in files:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_STORED
            header_end = buffer.tell() + zipfile.sizeFileHeader + len(name.encode("utf-8"))
            padding = -header_end % _USDZ_ALIGNMENT
            if 0 < padding < _MIN_EXTRA:
                padding += _USDZ_ALIGNMENT
            if padding:
                info.extra = struct.pack("<HH", _PAD_FIELD_ID, padding - _MIN_EXTRA) + b"\0" * (padding - _MIN_EXTRA)
            zf.writestr(info, payload)
    return buffer.getvalue()


def build_usdz(
    panels: list[PanelPlacement],
    tilt_deg: float,
    azimuth_deg: float,
    zone: str,
) -> UsdzModel:
    scale = _tabletop_scale(panels)
    usda = build_usda(panels, tilt_deg, azimuth_deg, zone, scale)
    # The root layer must be the archive's first entry; readers take it as the
    # thing to open.
    data = _aligned_zip([(f"nongfab-{zone}.usda", usda.encode("utf-8"))])
    return UsdzModel(data=data, scale=scale, panel_count=len(panels))


def _tabletop_scale(panels: list[PanelPlacement]) -> float:
    """Shrink the array to something that fits on a table.

    Mirrors `web/src/lib/xr.ts`'s `tabletopScale`, on the same reasoning: at 1:1
    an AR visitor stands inside a structure larger than the room.
    """
    if not panels:
        return 1.0
    span = max(
        max(p.east_m for p in panels) - min(p.east_m for p in panels),
        max(p.north_m for p in panels) - min(p.north_m for p in panels),
        1.0,
    )
    return TABLETOP_SPAN_M / span
