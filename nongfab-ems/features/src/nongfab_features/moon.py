"""Topocentric lunar position (azimuth/elevation), for Solar3DPage's "moon
rises to replace the sun after sunset" feature (2026-07-18 user request -
"ตรง 3D ให้ทำดวงจันทร์เพิ่ม...มาขึ้นแทนดวงอาทิตย์ เมื่อดวงอาทิตย์ตกดินไปเเล้ว").

pvlib (clearsky.py's own solar-position source) only computes solar
position - there is no lunar equivalent in it or anywhere else already
installed in this project (checked: no ephem/skyfield/astropy dependency
exists). Rather than add a new heavyweight ephemeris dependency (skyfield
needs a downloaded JPL kernel file; pyephem is a C extension) for a
decorative visual, this implements the well-known compact algorithm from
Paul Schlyter's "How to Compute Planetary Positions" (the same
periodic-terms approach summarized in more precise form in Meeus'
"Astronomical Algorithms") directly in pure Python/numpy - geocentric
ecliptic orbital elements, the dominant ~13 solar-perturbation correction
terms, then the standard ecliptic -> equatorial -> topocentric-horizontal
rotation chain (the same last step pvlib performs internally for the sun).

Honesty caveat, worth stating plainly: this is a low/medium-precision
approximation (typically within roughly one degree for the position terms
used here), not the same precision-audited pipeline pvlib provides for the
sun. That's more than sufficient for this scene's own decorative purpose (a
moon that visibly rises, arcs, and sets in roughly the right place) - it is
NOT meant to support anything that needs arcminute-grade lunar accuracy
(eclipse/occultation timing, etc.). A real ephemeris library should replace
this, not extend it, if such a need ever arises.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

_EPOCH = datetime(1999, 12, 31, 0, 0, 0, tzinfo=timezone.utc)  # Schlyter's d=0 reference instant


def _days_since_epoch(when: datetime) -> float:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when - _EPOCH).total_seconds() / 86400.0


def _norm_deg(x: float) -> float:
    return x % 360.0


def moon_illumination(when: datetime) -> tuple[float, bool]:
    """Returns (illuminated_fraction, waxing) for the Moon at `when`:
    `illuminated_fraction` is 0.0 (new moon) .. 1.0 (full moon), `waxing` is
    True while the lit fraction is growing (new -> full), False while shrinking
    (full -> new). Used only to draw a phase-correct crescent/gibbous marker in
    the 3D view - a decorative refinement, same low/medium-precision caveat as
    `moon_position` (this file's own header).

    Uses the Moon's mean elongation from the Sun, D = Lm - Ls (the exact same
    quantity `moon_position` already computes for its perturbation terms): the
    illuminated fraction is (1 - cos D) / 2, and the Moon is waxing while D is
    in (0, 180) - i.e. the Moon is east of the Sun, rising/setting after it.
    Mean (not fully perturbed) longitudes are plenty for choosing how fat a
    crescent to draw; nobody reads phase to arc-minute accuracy off a marker.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    d = _days_since_epoch(when)

    sun_w = _norm_deg(282.9404 + 4.70935e-5 * d)
    sun_M = _norm_deg(356.0470 + 0.9856002585 * d)
    ls = _norm_deg(sun_M + sun_w)  # Sun's mean longitude

    moon_N = _norm_deg(125.1228 - 0.0529538083 * d)
    moon_w = _norm_deg(318.0634 + 0.1643573223 * d)
    moon_M = _norm_deg(115.3654 + 13.0649929509 * d)
    lm = _norm_deg(moon_N + moon_w + moon_M)  # Moon's mean longitude

    elongation = _norm_deg(lm - ls)
    fraction = (1.0 - math.cos(math.radians(elongation))) / 2.0
    waxing = elongation < 180.0
    return fraction, waxing


def moon_position(when: datetime, latitude: float, longitude: float) -> tuple[float, float]:
    """Returns (azimuth_deg, elevation_deg) of the Moon as seen from
    (latitude, longitude) at `when` - same (azimuth_deg, elevation_deg)
    convention as `clearsky.compute_clearsky_and_position`'s solar position
    (azimuth measured clockwise from North, elevation positive above the
    horizon), so the frontend can treat sun and moon positions identically.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    d = _days_since_epoch(when)

    # Sun's own orbital elements - needed both for the Moon's perturbation
    # terms below and to derive Greenwich Mean Sidereal Time. Its ascending
    # node and inclination are conventionally 0 (by definition of the
    # ecliptic plane) and its semi-major axis is irrelevant here (only
    # direction matters, not distance), so unlike the Moon's own elements
    # below, those three are never assigned - only the ones actually used.
    sun_w = _norm_deg(282.9404 + 4.70935e-5 * d)
    sun_e = 0.016709 - 1.151e-9 * d
    sun_M = _norm_deg(356.0470 + 0.9856002585 * d)
    sun_E = sun_M + (180.0 / math.pi) * sun_e * math.sin(math.radians(sun_M)) * (1 + sun_e * math.cos(math.radians(sun_M)))
    sun_xv = math.cos(math.radians(sun_E)) - sun_e
    sun_yv = math.sin(math.radians(sun_E)) * math.sqrt(1 - sun_e * sun_e)
    sun_v = math.degrees(math.atan2(sun_yv, sun_xv))
    sun_lon = _norm_deg(sun_v + sun_w)

    # Moon's own orbital elements at epoch (Schlyter's integer-degree-precision constants).
    N = _norm_deg(125.1228 - 0.0529538083 * d)
    i = 5.1454
    w = _norm_deg(318.0634 + 0.1643573223 * d)
    a = 60.2666  # Earth radii
    e = 0.054900
    M = _norm_deg(115.3654 + 13.0649929509 * d)

    E = M + (180.0 / math.pi) * e * math.sin(math.radians(M)) * (1 + e * math.cos(math.radians(M)))
    for _ in range(2):  # 2 refinement passes - e is small (0.05), converges quickly
        E = E - (E - (180.0 / math.pi) * e * math.sin(math.radians(E)) - M) / (1 - e * math.cos(math.radians(E)))

    xv = a * (math.cos(math.radians(E)) - e)
    yv = a * (math.sqrt(1 - e * e) * math.sin(math.radians(E)))
    v = math.degrees(math.atan2(yv, xv))
    r = math.sqrt(xv * xv + yv * yv)

    vw = math.radians(v + w)
    Nr, ir = math.radians(N), math.radians(i)
    xh = r * (math.cos(Nr) * math.cos(vw) - math.sin(Nr) * math.sin(vw) * math.cos(ir))
    yh = r * (math.sin(Nr) * math.cos(vw) + math.cos(Nr) * math.sin(vw) * math.cos(ir))
    zh = r * (math.sin(vw) * math.sin(ir))

    lon_ecl = math.degrees(math.atan2(yh, xh))
    lat_ecl = math.degrees(math.atan2(zh, math.sqrt(xh * xh + yh * yh)))

    # Dominant perturbation terms from the Sun's gravity on the Moon's
    # position (Evection, Variation, Yearly equation, etc.) - the largest
    # ~13 terms, dropping the many smaller sub-0.01-degree ones Meeus' full
    # series carries, per this module's own precision caveat above.
    Ms = sun_M
    Lm = _norm_deg(N + w + M)  # Moon's mean longitude
    Ls = _norm_deg(sun_M + sun_w)  # Sun's mean longitude
    D = _norm_deg(Lm - Ls)  # elongation
    F = _norm_deg(Lm - N)  # argument of latitude

    def s(deg: float) -> float:
        return math.sin(math.radians(deg))

    lon_ecl += (
        -1.274 * s(M - 2 * D) + 0.658 * s(2 * D) - 0.186 * s(Ms) - 0.059 * s(2 * M - 2 * D)
        - 0.057 * s(M - 2 * D + Ms) + 0.053 * s(M + 2 * D) + 0.046 * s(2 * D - Ms) + 0.041 * s(M - Ms)
        - 0.035 * s(D) - 0.031 * s(M + Ms) - 0.015 * s(2 * F - 2 * D) + 0.011 * s(M - 4 * D)
    )
    lat_ecl += -0.173 * s(F - 2 * D) - 0.055 * s(M - F - 2 * D) - 0.046 * s(M + F - 2 * D) + 0.033 * s(F + 2 * D) + 0.017 * s(2 * M + F)

    # Ecliptic -> equatorial (RA/Dec), using Earth's obliquity at epoch.
    ecl = math.radians(23.4393 - 3.563e-7 * d)
    lon_r, lat_r = math.radians(lon_ecl), math.radians(lat_ecl)
    xe = math.cos(lon_r) * math.cos(lat_r)
    ye = math.sin(lon_r) * math.cos(lat_r)
    ze = math.sin(lat_r)
    xeq = xe
    yeq = ye * math.cos(ecl) - ze * math.sin(ecl)
    zeq = ye * math.sin(ecl) + ze * math.cos(ecl)
    ra = math.degrees(math.atan2(yeq, xeq))
    dec = math.degrees(math.atan2(zeq, math.sqrt(xeq * xeq + yeq * yeq)))

    # Equatorial -> topocentric horizontal (alt/az), via Greenwich Mean
    # Sidereal Time - the same final rotation step pvlib performs
    # internally for the sun, just done by hand here since pvlib has no
    # lunar equivalent to call.
    ut_hours = when.hour + when.minute / 60.0 + when.second / 3600.0
    gmst0 = _norm_deg(sun_lon + 180.0)
    gmst = _norm_deg(gmst0 + ut_hours * 15.0)
    lst = _norm_deg(gmst + longitude)
    ha = math.radians(_norm_deg(lst - ra))
    dec_r = math.radians(dec)
    lat_r_obs = math.radians(latitude)

    x = math.cos(ha) * math.cos(dec_r)
    y = math.sin(ha) * math.cos(dec_r)
    z = math.sin(dec_r)
    xhor = x * math.sin(lat_r_obs) - z * math.cos(lat_r_obs)
    yhor = y
    zhor = x * math.cos(lat_r_obs) + z * math.sin(lat_r_obs)

    azimuth_deg = _norm_deg(math.degrees(math.atan2(yhor, xhor)) + 180.0)
    elevation_deg = math.degrees(math.atan2(zhor, math.sqrt(xhor * xhor + yhor * yhor)))

    return azimuth_deg, elevation_deg
