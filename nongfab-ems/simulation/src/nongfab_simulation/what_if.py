"""What-if scenario adjustment: given a baseline power series (e.g. Module 4's
forecast, or loss_model's simulated output), recompute it under a different
cloud cover, curtailment, or degradation assumption - per the architecture
doc's Module 5 spec ("ปรับ cloud cover, curtailment level, degradation rate
แล้วดูผลต่อ output").
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ScenarioParams:
    """All deltas are relative adjustments, not absolute replacements - a
    scenario answers "what if conditions were X% different from the
    baseline", not "what if the value were exactly X".
    """

    # Additional cloud attenuation beyond the baseline, in percentage points
    # of power (e.g. +20 means 20% more power is lost to cloud than the
    # baseline already assumed; negative means clearer skies than baseline).
    extra_cloud_attenuation_pct: float = 0.0
    # Grid curtailment: this fraction of otherwise-available power is not
    # exported (e.g. 10.0 means 10% curtailed).
    curtailment_pct: float = 0.0
    # Linear panel degradation per year since commissioning (typical
    # crystalline-silicon warranty terms cite ~0.4-0.7%/year; not a
    # site-specific measurement - see README).
    degradation_pct_per_year: float = 0.0


def apply_scenario(baseline_power_kw: pd.Series, params: ScenarioParams, years_since_commissioning: float = 0.0) -> pd.Series:
    """Applies all three adjustments multiplicatively to `baseline_power_kw`
    and clips at 0 (a large enough extra_cloud_attenuation_pct or
    curtailment_pct can otherwise drive power negative, which isn't physical).
    """
    for name, value in (
        ("extra_cloud_attenuation_pct", params.extra_cloud_attenuation_pct),
        ("curtailment_pct", params.curtailment_pct),
        ("degradation_pct_per_year", params.degradation_pct_per_year),
    ):
        if value < -100:
            raise ValueError(f"{name} cannot reduce power by more than 100%, got {value}")
    if years_since_commissioning < 0:
        raise ValueError("years_since_commissioning cannot be negative")

    cloud_factor = 1 - params.extra_cloud_attenuation_pct / 100
    curtailment_factor = 1 - params.curtailment_pct / 100
    degradation_factor = 1 - (params.degradation_pct_per_year / 100) * years_since_commissioning
    degradation_factor = max(degradation_factor, 0.0)

    adjusted = baseline_power_kw * cloud_factor * curtailment_factor * degradation_factor
    return adjusted.clip(lower=0)
