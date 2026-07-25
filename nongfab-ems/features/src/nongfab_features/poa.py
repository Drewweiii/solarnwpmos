"""Horizontal irradiance -> what a tilted panel actually sees (2026-07-25).

The gap this closes. Every irradiance source feeding this system - GFS SSRD,
Himawari, PVGIS, the clear-sky model - reports GHI, which is irradiance on a
HORIZONTAL surface. The PV model consumed it directly, so a 10-degree array and
a flat one were indistinguishable to it: tilt changed the self-shading number
and nothing else. Project D's optimiser needed plane-of-array irradiance to say
anything at all about angles, and this is that calculation, promoted out of the
optimiser so the main pipeline can use it too.

Two steps, both standard:

1. DECOMPOSITION (Erbs). A GHI reading does not say how much arrived straight
   from the sun and how much was scattered, and the two land on a tilted plane
   very differently. Erbs infers the split from the clearness index - the
   ratio of GHI to what would arrive above the atmosphere. It is the standard
   choice when only GHI is measured, which is every source here.

2. TRANSPOSITION (Hay-Davies). Projects beam, sky-diffuse and ground-reflected
   onto the tilted plane. Hay-Davies rather than isotropic because it keeps the
   circumsolar part of the diffuse, which is what actually separates one
   orientation from another near the optimum.

Honest about what it is: a model, not a measurement. There is no pyranometer in
the array plane here (there is no generation meter either - see the project's
standing note), so POA is inferred from GHI the same way commercial yield
software does it. The uncertainty it adds is real but small next to the error it
removes, which was treating tilted panels as flat.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib

from .clearsky import nong_fab_site_location

# Ground reflectance for the ground-reflected term. pvlib's own default and a
# standard figure for mixed industrial ground - not a site measurement. At the
# shallow tilts used here the ground-reflected term is small, so this matters
# far less than the beam split does.
DEFAULT_ALBEDO = 0.25


def poa_from_ghi(
    ghi: np.ndarray | pd.Series,
    index: pd.DatetimeIndex,
    tilt_deg: float,
    azimuth_deg: float,
    latitude: float | None = None,
    longitude: float | None = None,
    albedo: float = DEFAULT_ALBEDO,
) -> np.ndarray:
    """Global plane-of-array irradiance (W/m2) for a fixed-tilt surface.

    `index` may be tz-naive; it is then read as UTC, which is what every
    upstream source in this project publishes. Getting that wrong would shift
    the sun by hours and silently corrupt every value, so it is handled here
    rather than left to each caller to remember.

    A horizontal surface (tilt 0) is returned unchanged apart from floating
    point: there is nothing to transpose, and passing it through the model
    anyway would introduce a small error where the answer is exactly known.
    """
    ghi_array = np.asarray(ghi, dtype=float)
    ghi_array = np.nan_to_num(ghi_array, nan=0.0, posinf=0.0, neginf=0.0)
    if tilt_deg == 0.0:
        return ghi_array

    if index.tz is None:
        index = index.tz_localize("UTC")

    if latitude is None or longitude is None:
        latitude, longitude = nong_fab_site_location()

    solpos = pvlib.solarposition.get_solarposition(index, latitude, longitude)
    zenith = solpos["apparent_zenith"]
    ghi_series = pd.Series(ghi_array, index=index)

    # Erbs needs the true (not apparent) zenith's day-of-year companion; pvlib
    # takes the datetime index and derives extraterrestrial radiation itself.
    decomposed = pvlib.irradiance.erbs(ghi_series, zenith, index)
    dni = decomposed["dni"].fillna(0.0)
    dhi = decomposed["dhi"].fillna(0.0)

    total = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt_deg,
        surface_azimuth=azimuth_deg,
        solar_zenith=zenith,
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi_series,
        dhi=dhi,
        dni_extra=pvlib.irradiance.get_extra_radiation(index),
        albedo=albedo,
        model="haydavies",
    )
    poa = np.nan_to_num(total["poa_global"].to_numpy(), nan=0.0, posinf=0.0, neginf=0.0)
    # Night stays night. Erbs can emit tiny positive values at zenith angles
    # past 90 degrees, and letting those through would have the array producing
    # after dark.
    return np.where(ghi_array > 0.0, np.maximum(poa, 0.0), 0.0)
