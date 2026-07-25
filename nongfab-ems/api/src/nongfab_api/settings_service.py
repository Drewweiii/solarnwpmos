"""Pushes the effective settings into the places that can't read them
per-request (2026-07-25).

Two kinds of consumer, and the difference is the whole reason this module
exists:

- **Read per request.** A route that already computes something can just call
  `settings_store.effective("...")` when it runs. That covers the look-back
  windows, diagnostic thresholds, the expansion plan and the financial defaults.
  Nothing to do here.
- **Needs injection.** `nongfab_common.assets` and
  `nongfab_simulation.loss_model` are used deep inside pure computation packages
  that have no handle on the app database, and they're called from synchronous
  code (physics, per-zone simulation). Those get pushed the values instead, the
  same pattern `soiling_service.refresh_measured_soiling` already established.

`apply_effective_settings` is idempotent and safe to call on every write, and is
called once at startup after the store loads. A zone/site override of 0 means
"leave config/assets.yaml alone" (see the registry's own note), which is what
lets the as-built YAML stay the source of truth until somebody deliberately
changes a field.
"""

from __future__ import annotations

import logging

from nongfab_common.assets import set_asset_overrides
from nongfab_features.shading import annual_shading_loss_pct
from nongfab_simulation.loss_model import set_loss_overrides

from .settings_registry import ZONES
from .settings_store import effective

logger = logging.getLogger(__name__)

# settings key -> LossFactors field name that loss_model accepts.
_LOSS_KEY_MAP = {
    "losses.external_shading_pct": "shading_pct",
    "losses.mismatch_pct": "mismatch_pct",
    "losses.dc_wiring_pct": "dc_wiring_pct",
    "losses.connections_pct": "connections_pct",
    "losses.availability_pct": "availability_pct",
    "losses.soiling_fallback_land_pct": "soiling_fallback_land_pct",
    "losses.soiling_fallback_marine_pct": "soiling_fallback_marine_pct",
}

# settings key -> dotted path the assets override hook understands.
_SITE_KEYS = ("site.facility_electrical_load_kw", "site.facility_annual_electricity_cost_thb")
_ZONE_FIELDS = ("ac_capacity_kw", "dc_capacity_kwp", "tilt_deg", "azimuth_deg")


def asset_override_payload() -> dict[str, float]:
    """The asset overrides implied by the current settings. A zone/site value of
    0 is skipped - that is the registry's "use the as-built YAML" sentinel, and
    writing a real 0 into a capacity or tilt would be nonsense anyway."""
    payload: dict[str, float] = {}
    for key in _SITE_KEYS:
        value = effective(key)
        if value > 0:
            payload[key] = value
    for zone in ZONES:
        for field in _ZONE_FIELDS:
            value = effective(f"zone.{zone}.{field}")
            if value > 0:
                payload[f"zone.{zone}.{field}"] = value
    return payload


def loss_override_payload() -> dict[str, float]:
    """The loss-factor overrides implied by the current settings. Only values
    that actually differ from the module's own default are published, so an
    untouched form doesn't fill the override dict with restatements of the
    defaults (which would make `loss_overrides()` a useless signal)."""
    from nongfab_simulation import loss_model

    module_defaults = {
        "shading_pct": loss_model.DEFAULT_EXTERNAL_SHADING_PCT,
        "mismatch_pct": loss_model.DEFAULT_MISMATCH_PCT,
        "dc_wiring_pct": loss_model.DEFAULT_DC_WIRING_PCT,
        "connections_pct": loss_model.DEFAULT_CONNECTIONS_PCT,
        "availability_pct": loss_model.DEFAULT_AVAILABILITY_PCT,
        "soiling_fallback_land_pct": loss_model.DEFAULT_SOILING_PCT_LAND,
        "soiling_fallback_marine_pct": loss_model.DEFAULT_SOILING_PCT_MARINE,
    }
    payload: dict[str, float] = {}
    for key, field in _LOSS_KEY_MAP.items():
        value = effective(key)
        if value != module_defaults[field]:
            payload[field] = value
    return payload


def apply_effective_settings() -> None:
    """Publish the current effective settings to every injected consumer.

    Also clears the two lru_caches that are computed FROM these settings and
    would otherwise keep answering with pre-edit values for the life of the
    process: `annual_shading_loss_pct` (per zone, from tilt/azimuth/geometry)
    `/grid/carbon`'s cached clear-sky day profile (per date, from each zone's
    capacity, tilt and loss factors), and `/orientation`'s cached tilt sweep
    (per zone, from its tilt, azimuth and row pitch).
    """
    from nongfab_simulation.tilt_optimizer import optimise_zone

    from .routes_grid_carbon import _profile_for_day

    set_asset_overrides(asset_override_payload())
    set_loss_overrides(loss_override_payload())
    annual_shading_loss_pct.cache_clear()
    _profile_for_day.cache_clear()
    optimise_zone.cache_clear()
    logger.debug("settings applied to assets + loss model")
