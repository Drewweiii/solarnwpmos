"""When does the forecast fail? (2026-07-25, project C)

Verification reports one RMSE per zone. That single number averages a January
morning with no cloud in it together with an afternoon of monsoon convection,
and a model can post a respectable figure by being good at the easy half. Solar
forecasting work is expected to report performance BY SKY CONDITION for exactly
that reason: the interesting question is not "how big is the error" but "which
conditions is this model helpless in".

The classifier is the clear-sky index, kt = GHI / GHI_clearsky - the same signal
`nongfab_features.clearsky.clear_sky_index` already computes for the hour-ahead
feature set, reused here rather than reinvented. Near 1 the sky is clear; the
lower it goes the more cloud sits between the panel and the sun.

THE THRESHOLDS ARE CONVENTION, NOT MEASUREMENT. The 0.7 / 0.3 split follows the
common three-way partition used in the solar-forecasting literature; nobody
measured it at Nong Fab, and no measurement here could - it is a definition, not
a property of the site. They are therefore exposed as settings, so a reader who
prefers a different partition can move them and see the tables change instead of
arguing with a hardcoded number.

One consequence worth stating plainly: kt needs a clear-sky reference, which is
zero at night. Night hours have no defined sky condition and are excluded rather
than bucketed - the same daylight-only rule the rest of verification already
applies, arrived at for the same reason.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

# Labels are stable identifiers, not display text - the frontend maps them to
# Thai. A label change would silently break the mapping, so they are constants.
SKY_CLEAR = "clear"
SKY_PARTLY = "partly_cloudy"
SKY_OVERCAST = "overcast"

SKY_ORDER: tuple[str, ...] = (SKY_CLEAR, SKY_PARTLY, SKY_OVERCAST)

# kt at or above this is a clear sky; below the overcast threshold is overcast;
# in between is partly cloudy. Convention - see the module docstring.
DEFAULT_CLEAR_KT = 0.7
DEFAULT_OVERCAST_KT = 0.3

# Below this clear-sky GHI the reference is too small to divide by: kt explodes
# and the classification becomes noise. These hours are night or the few minutes
# either side of it.
MIN_CLEARSKY_GHI_W_M2 = 20.0


def classify_kt(
    kt: float | None,
    clear_kt: float = DEFAULT_CLEAR_KT,
    overcast_kt: float = DEFAULT_OVERCAST_KT,
) -> str | None:
    """Bucket one clear-sky index. None in, None out - an hour with no usable
    kt is unclassified, which is a different thing from overcast and must not be
    quietly folded into it."""
    if kt is None or not np.isfinite(kt):
        return None
    if kt >= clear_kt:
        return SKY_CLEAR
    if kt < overcast_kt:
        return SKY_OVERCAST
    return SKY_PARTLY


def kt_by_hour(
    nwp: pd.DataFrame,
    latitude: float,
    longitude: float,
    min_clearsky_ghi: float = MIN_CLEARSKY_GHI_W_M2,
) -> dict[datetime, float]:
    """Clear-sky index per target hour, from the NWP history.

    `nwp` is `RealDataStore.nwp_history_df()`: many rows per `valid_time`, one
    per issue. The FRESHEST issue for each valid_time is taken, because that is
    the closest thing this system has to "the weather that actually happened" -
    the same choice the actual-power side of verification already makes, and
    using an old issue here would classify an hour by a forecast that the later
    issue went on to correct.

    Hours whose clear-sky reference is too small to divide by are omitted
    entirely rather than returned as a huge or zero kt.
    """
    if nwp is None or len(nwp) == 0:
        return {}
    if "valid_time" not in nwp or "ssrd_w_m2" not in nwp:
        return {}

    # Freshest issue wins per valid_time.
    latest = nwp.sort_values("issue_time").groupby("valid_time", as_index=False).last()
    index = pd.DatetimeIndex(latest["valid_time"])
    if index.tz is None:
        index = index.tz_localize("UTC")

    # Imported here rather than at module scope: this module is otherwise pure
    # arithmetic, and pvlib is heavy enough that the classification helpers
    # above stay importable and testable without it.
    from nongfab_features.clearsky import clear_sky_index, compute_clearsky_and_position

    sky = compute_clearsky_and_position(index, latitude, longitude)
    measured = pd.Series(latest["ssrd_w_m2"].to_numpy(dtype=float), index=index)
    kt = clear_sky_index(measured, sky["ghi_clearsky"])

    usable = sky["ghi_clearsky"] >= min_clearsky_ghi
    return {
        ts.to_pydatetime(): float(value)
        for ts, value, ok in zip(index, kt.to_numpy(), usable.to_numpy())
        if ok and np.isfinite(value)
    }


def sky_label_for(
    target_time: datetime,
    kt_lookup: dict[datetime, float],
    clear_kt: float = DEFAULT_CLEAR_KT,
    overcast_kt: float = DEFAULT_OVERCAST_KT,
) -> str | None:
    """The sky condition at one target hour, or None when it cannot be told.

    None is a real answer here: no NWP row for that hour, or a clear-sky
    reference too small to divide by. Guessing a bucket would put hours into a
    table that the data cannot place.
    """
    return classify_kt(kt_lookup.get(target_time), clear_kt, overcast_kt)
