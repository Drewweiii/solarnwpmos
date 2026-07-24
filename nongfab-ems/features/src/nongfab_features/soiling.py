"""Marine soiling / salt-spray feature engineering (2026-07-24).

Nong Fab is a coastal LNG-terminal site on the Gulf of Thailand: sea-salt
aerosol carried inland by onshore wind deposits on the PV glass (soiling) and,
combined with humidity, both attenuates irradiance and dulls module output. The
literature (see forecast/README.md's feature notes) shows coastal PV forecasts
improve when the model can "see" these marine-aerosol drivers rather than
treating soiling as a static derate.

Every function here is pure and vectorized (accepts Python scalars OR NumPy
arrays / pandas Series), so the exact same code builds the training frame and
the single-row serving input - no train/serve skew. Nothing here fetches data;
it derives features from values the NWP history store already keeps
(wind10m_u_ms, wind10m_v_ms, relative_humidity_pct, precip_mm).
"""

from __future__ import annotations

import numpy as np

# The Gulf of Thailand lies to the SOUTH of Nong Fab (the jetty runs south into
# the sea - see config/assets.yaml). "Onshore" wind (sea -> land, the salt-
# carrying direction) therefore blows FROM the south, i.e. a meteorological
# "wind from" bearing near 180 deg.
NONG_FAB_SEA_BEARING_DEG = 180.0

# Wind speed (m/s) that maps the onshore component to a ~full-scale salt load;
# above this the index saturates. 10 m/s is a strong sea breeze.
SALT_WIND_REFERENCE_MS = 10.0


def wind_speed_ms(u_ms, v_ms):
    """Scalar wind speed from 10 m u/v components. NaN components -> 0."""
    u = np.nan_to_num(np.asarray(u_ms, dtype=float))
    v = np.nan_to_num(np.asarray(v_ms, dtype=float))
    return np.hypot(u, v)


def wind_from_bearing_deg(u_ms, v_ms):
    """Meteorological 'direction the wind blows FROM', degrees clockwise from
    north (0=N, 90=E, 180=S, 270=W). Calm -> 0."""
    u = np.nan_to_num(np.asarray(u_ms, dtype=float))
    v = np.nan_to_num(np.asarray(v_ms, dtype=float))
    # atan2(-u, -v) gives the "from" direction in the met convention.
    return np.mod(np.degrees(np.arctan2(-u, -v)), 360.0)


def onshore_factor(u_ms, v_ms, sea_bearing_deg: float = NONG_FAB_SEA_BEARING_DEG):
    """How aligned the wind is with the sea->land direction: 1 when it blows
    straight off the sea, 0 when it blows from land (or calm). cos of the
    angular difference, clamped at 0 (offshore wind carries no sea salt)."""
    frm = wind_from_bearing_deg(u_ms, v_ms)
    diff = np.radians(frm - sea_bearing_deg)
    aligned = np.cos(diff)
    calm = wind_speed_ms(u_ms, v_ms) < 1e-6
    return np.where(calm, 0.0, np.clip(aligned, 0.0, 1.0))


def salt_soiling_index(
    u_ms,
    v_ms,
    relative_humidity_pct,
    sea_bearing_deg: float = NONG_FAB_SEA_BEARING_DEG,
    wind_reference_ms: float = SALT_WIND_REFERENCE_MS,
):
    """A 0..1 marine-soiling proxy: onshore wind speed (how much salt spray is
    driven toward the array) scaled by humidity (hygroscopic salt aerosol grows
    and adheres more in moist air). Instantaneous - depends only on the row's
    own values, so training and serving compute it identically. High when a
    strong humid sea breeze blows onto the site; ~0 for dry offshore wind."""
    onshore_speed = onshore_factor(u_ms, v_ms, sea_bearing_deg) * wind_speed_ms(u_ms, v_ms)
    speed_term = np.clip(onshore_speed / wind_reference_ms, 0.0, 1.0)
    rh = np.nan_to_num(np.asarray(relative_humidity_pct, dtype=float))
    rh_term = np.clip(rh / 100.0, 0.0, 1.0)
    return speed_term * rh_term
