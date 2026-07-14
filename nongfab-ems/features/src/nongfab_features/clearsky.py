"""Clear-sky model (pvlib, Ineichen) and solar position for Nong Fab, plus the
clear-sky index (measured / clear-sky GHI) used throughout the rest of this
module (daytime filtering, QC, feature engineering).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib
from nongfab_common.assets import load_assets


def nong_fab_site_location() -> tuple[float, float]:
    """(latitude, longitude) of the plant's nominal center, from config/assets.yaml -
    the single source of truth other modules should use too, not a hardcoded duplicate.
    """
    registry = load_assets()
    return registry.site.nominal_center.lat, registry.site.nominal_center.lon


def compute_clearsky_and_position(
    index: pd.DatetimeIndex, latitude: float, longitude: float, altitude: float = 0.0, tz: str = "UTC"
) -> pd.DataFrame:
    """Returns a DataFrame aligned to `index` with columns: ghi_clearsky,
    dni_clearsky, dhi_clearsky (Ineichen model), zenith_deg, elevation_deg,
    azimuth_deg. `index` must be timezone-aware (pvlib requires it for solar
    position accuracy).
    """
    if index.tz is None:
        raise ValueError("index must be timezone-aware (e.g. tz='UTC') for accurate solar position")

    location = pvlib.location.Location(latitude, longitude, tz=tz, altitude=altitude)
    solpos = location.get_solarposition(index)
    clearsky = location.get_clearsky(index, model="ineichen")

    return pd.DataFrame(
        {
            "ghi_clearsky": clearsky["ghi"],
            "dni_clearsky": clearsky["dni"],
            "dhi_clearsky": clearsky["dhi"],
            "zenith_deg": solpos["zenith"],
            "elevation_deg": solpos["elevation"],
            "azimuth_deg": solpos["azimuth"],
        },
        index=index,
    )


def clear_sky_index(ghi_measured: pd.Series, ghi_clearsky: pd.Series, clip_max: float = 2.0) -> pd.Series:
    """CSI = measured GHI / clear-sky GHI - the paper's normalized irradiance signal
    (≈1 under clear sky, <1 under cloud, occasionally >1 under cloud-edge
    enhancement). Clipped to [0, clip_max] and NaN where clear-sky GHI is ~0
    (night, or numerically unstable near sunrise/sunset) rather than blowing up.
    """
    safe_clearsky = ghi_clearsky.where(ghi_clearsky > 1.0)  # < 1 W/m^2 is effectively night
    with np.errstate(divide="ignore", invalid="ignore"):
        csi = ghi_measured / safe_clearsky
    return csi.clip(lower=0, upper=clip_max)
