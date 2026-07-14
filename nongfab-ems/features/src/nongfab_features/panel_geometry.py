"""Per-zone 3D panel layout - Feature B/C's geometric foundation (Module 7's
3D shading/solar-access view + sun-path sweep). Converts each zone's
surveyed corner lat/lon (config/assets.yaml) into a local flat-earth (east,
north) meter grid centered on the zone's centroid, then places individual
panels within it.

Real per-sub-array string/module layout only exists for Jetty (`sub_arrays`
in config/assets.yaml - the 4 built sub-arrays' strings x modules_per_string
sum to exactly 320, Jetty's module_count; the 5th entry, "05A", is a
documented future phase with no module count yet and is skipped). GIS/ISB
have no sub-array breakdown (their SLD is electrical-only, not surveyed to
that granularity), so each is rendered as a single rectangular block sized
to `module_count`, factored to a near-square row/column grid - a
visualization approximation, not a claim about real physical string
boundaries. Only Jetty's block layout reflects real hardware groupings.

tilt_deg/azimuth_deg are null in config/assets.yaml for every zone (not
field-surveyed - see Zone's own docstring in nongfab_common.assets).
DEFAULT_TILT_DEG/DEFAULT_AZIMUTH_DEG below are literature-typical
assumptions for a fixed-tilt array at this near-equator latitude (~12.7N),
used only where a zone's own value is None - not a measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nongfab_common.assets import AssetRegistry, Zone, load_assets

# A lower-than-latitude tilt (10 deg, vs. the ~13 deg "tilt = latitude" rule
# of thumb) is common practice for fixed-tilt arrays in tropical Southeast
# Asia, trading a little annual yield for lower wind loading/structure cost;
# 180 deg (south-facing) is the standard fixed-tilt convention in the
# Northern Hemisphere. Neither is a site-specific measurement.
DEFAULT_TILT_DEG = 10.0
DEFAULT_AZIMUTH_DEG = 180.0

# Jetty's own structure - a ~1.25km-long north-south trestle
# (`span_north_south_km`) - makes a south-facing default physically wrong: a
# string's modules_per_string run *along* the row-length axis, and a
# south-facing orientation would swing that axis east-west, i.e. hanging
# ~48m off the side of a narrow trestle catwalk. Facing the array east/west
# instead keeps a string's own length running north-south, along the
# trestle's actual run - not a measurement either, just the one azimuth
# choice that fits the structure it's mounted on (arbitrarily west, 270 deg;
# a real design could equally choose east given how little east/west yield
# differs this close to the equator).
JETTY_DEFAULT_AZIMUTH_DEG = 270.0

# No sub-array-level row-spacing survey exists for any zone; a typical
# ground-mount fixed-tilt row pitch, kept just wide enough to clear a
# panel's own slant footprint at DEFAULT_TILT_DEG.
DEFAULT_ROW_PITCH_M = 3.0

# Real module (Trina Vertex N TSM-NEG21C.20, config/assets.yaml's
# module_detail): 2384 x 1303 mm, mounted landscape (long side along the
# row, short side in the tilt/slant direction) - a common fixed-tilt
# orientation that keeps row-pitch requirements (and self-shading) lower
# than portrait mounting; used as the fallback if a zone lacks module_detail.
_FALLBACK_MODULE_LONG_MM = 2384.0
_FALLBACK_MODULE_SHORT_MM = 1303.0

# Not surveyed at the sub-array level - purely a visual left/right
# separation for Jetty's trestle-side ("side": left/right) sub-arrays.
_JETTY_LATERAL_OFFSET_M = 6.0


@dataclass(frozen=True)
class Panel:
    """One physical module's position, in meters east/north of the zone's
    centroid. `row` counts away from the array's facing direction (`row ==
    0` is the front row, nearest to unobstructed sun - see shading.py); all
    panels in a block share the same tilt/azimuth (fixed-tilt array, no
    tracking).
    """

    block_id: str
    row: int
    col: int
    east_m: float
    north_m: float
    width_m: float
    slant_height_m: float
    tilt_deg: float
    azimuth_deg: float


@dataclass(frozen=True)
class ZoneLayout:
    zone_id: str
    tilt_deg: float
    azimuth_deg: float
    row_pitch_m: float
    panels: list[Panel]


def _module_dims_m(zone: Zone) -> tuple[float, float]:
    """(width_m along a row, slant_height_m in the tilt plane) - see module
    docstring for the landscape-mount assumption."""
    if zone.module_detail is not None:
        long_mm, short_mm = zone.module_detail.dimensions_mm[0], zone.module_detail.dimensions_mm[1]
    else:
        long_mm, short_mm = _FALLBACK_MODULE_LONG_MM, _FALLBACK_MODULE_SHORT_MM
    return long_mm / 1000, short_mm / 1000


def _row_pitch_m(slant_height_m: float, tilt_deg: float) -> float:
    """Just wide enough to clear the row in front's slant footprint, with a
    fixed floor for realism (real arrays don't pack rows edge-to-edge)."""
    return max(DEFAULT_ROW_PITCH_M, slant_height_m * math.cos(math.radians(tilt_deg)) + 0.5)


def _rotate_to_local_en(u_m: float, v_m: float, azimuth_deg: float) -> tuple[float, float]:
    """Rotates a panel's block-local (u = along a row, v = along the row-
    stacking/shading axis, v=0 at the front row) position into true (east,
    north) meters, given the array's compass facing direction. `azimuth_deg`
    follows the standard convention (0=N, 90=E, 180=S, 270=W); increasing v
    moves away from the facing direction (further "back", i.e. more likely
    shaded by the row in front when the sun is roughly aligned with the
    array's facing direction).
    """
    az = math.radians(azimuth_deg)
    east_m = u_m * math.cos(az) - v_m * math.sin(az)
    north_m = -u_m * math.sin(az) - v_m * math.cos(az)
    return east_m, north_m


def _grid_panels(
    block_id: str, rows: int, cols: int, width_m: float, slant_height_m: float,
    tilt_deg: float, azimuth_deg: float, row_pitch_m: float,
    origin_east_m: float = 0.0, origin_north_m: float = 0.0,
) -> list[Panel]:
    total_width_m = cols * width_m
    panels = []
    for row in range(rows):
        for col in range(cols):
            u_m = (col + 0.5) * width_m - total_width_m / 2
            v_m = row * row_pitch_m
            east_m, north_m = _rotate_to_local_en(u_m, v_m, azimuth_deg)
            panels.append(
                Panel(
                    block_id=block_id, row=row, col=col,
                    east_m=origin_east_m + east_m, north_m=origin_north_m + north_m,
                    width_m=width_m, slant_height_m=slant_height_m,
                    tilt_deg=tilt_deg, azimuth_deg=azimuth_deg,
                )
            )
    return panels


def _near_square_factors(n: int) -> tuple[int, int]:
    """Largest divisor pair of `n` closest to a square (rows <= cols) - used
    only for GIS/ISB's visualization-approximation block (see module
    docstring); falls back to a single row if `n` is prime.
    """
    rows = max(1, int(round(n**0.5)))
    while rows > 1 and n % rows != 0:
        rows -= 1
    return rows, n // rows


def _rectangular_block_layout(zone: Zone, tilt_deg: float, azimuth_deg: float) -> list[Panel]:
    width_m, slant_height_m = _module_dims_m(zone)
    row_pitch_m = _row_pitch_m(slant_height_m, tilt_deg)
    rows, cols = _near_square_factors(zone.module_count)
    return _grid_panels(f"{zone.id}-main", rows, cols, width_m, slant_height_m, tilt_deg, azimuth_deg, row_pitch_m)


def _jetty_layout(zone: Zone, tilt_deg: float, azimuth_deg: float) -> list[Panel]:
    width_m, slant_height_m = _module_dims_m(zone)
    row_pitch_m = _row_pitch_m(slant_height_m, tilt_deg)

    built = [sa for sa in zone.sub_arrays if sa.strings is not None and sa.modules_per_string is not None]
    if not built:
        return []

    span_m = (zone.span_north_south_km or 1.25) * 1000
    panels: list[Panel] = []
    for i, sub_array in enumerate(built):
        # Real inter-sub-array spacing isn't in config/assets.yaml (only
        # interconnection_points' distance-from-ISB is, which doesn't map
        # 1:1 to these 4 blocks) - spread evenly along the surveyed span,
        # "a line of installations along the trestle" rather than one block.
        along_span_north_m = (i + 0.5) / len(built) * span_m - span_m / 2
        lateral_east_m = (
            _JETTY_LATERAL_OFFSET_M if sub_array.side == "right"
            else -_JETTY_LATERAL_OFFSET_M if sub_array.side == "left"
            else 0.0
        )
        panels.extend(
            _grid_panels(
                sub_array.id, sub_array.strings, sub_array.modules_per_string, width_m, slant_height_m,
                tilt_deg, azimuth_deg, row_pitch_m,
                origin_east_m=lateral_east_m, origin_north_m=along_span_north_m,
            )
        )
    return panels


def generate_zone_layout(zone_id: str, registry: AssetRegistry | None = None) -> ZoneLayout:
    registry = registry or load_assets()
    zone = registry.zone(zone_id)  # raises KeyError for an unknown zone id

    tilt_deg = zone.tilt_deg if zone.tilt_deg is not None else DEFAULT_TILT_DEG
    default_azimuth = JETTY_DEFAULT_AZIMUTH_DEG if zone.id == "Jetty" else DEFAULT_AZIMUTH_DEG
    azimuth_deg = zone.azimuth_deg if zone.azimuth_deg is not None else default_azimuth

    if zone.id == "Jetty":
        panels = _jetty_layout(zone, tilt_deg, azimuth_deg)
    else:
        panels = _rectangular_block_layout(zone, tilt_deg, azimuth_deg)

    _, slant_height_m = _module_dims_m(zone)
    return ZoneLayout(
        zone_id=zone.id, tilt_deg=tilt_deg, azimuth_deg=azimuth_deg,
        row_pitch_m=_row_pitch_m(slant_height_m, tilt_deg), panels=panels,
    )
