"""Green-savings / carbon summary for the Energy Report page.

Given a zone's estimated solar generation, this computes - per time horizon
(1 day / 1 month / 1 year / 25-year project lifetime) - how much the solar
avoids in electricity cost, how much CO2 it keeps out of the grid, and how
much carbon credit it earns. It is a pure module (no FastAPI, no I/O) so the
numbers are unit-testable in isolation; the route (`routes_savings.py`) only
wires generation figures from the existing simulation pipeline into it.

All the money/emission constants below come from the real reference documents
the user supplied on 2026-07-19 (staged under
`docs/new-project-25yr-lifetime/reference-files|images/`), with the four
site-specific choices they confirmed the same day:

  * Voltage level ............ HV (>= 69 kV)      - PTT LNG Terminal 2 site
  * Normal tariff structure .. TOU, valued at the Peak energy rate, because
                               solar generates during the daytime Peak window
                               (a documented approximation - it does not net
                               out weekend/holiday off-peak hours; refine if a
                               real half-hourly consumption profile appears)
  * UGT2 portfolio ........... Portfolio A
  * Grid emission factor ..... 0.4999 kgCO2/kWh (TGO grid-mix, scope 2)

Rate sources (all baht per kWh, VAT excluded, matching the announcements):
  * Normal Type-4 (large) TOU, HV Peak = 4.1025
        -> "ประกาศ ... ประเภทที่ 4 กิจการขนาดใหญ่" (reference-images/yai.png, 4.2.1)
  * UGT1 retail premium = +0.0375 over the normal retail (Ft-included) rate
        -> "ประกาศอัตรา UGT1 ปี 2569" (reference-files/...UGT1...pdf & กฟผ.6/2569)
        UGT1 = normal retail total (incl. Ft) + Premium (P_REC + P_A)
  * UGT2 retail Portfolio A, HV = 4.0423
        -> "ประกาศอัตรา UGT2 ... ระดับขายปลีก" (reference-images/222.png)

Carbon (user-supplied rule-of-thumb + the carbon-credit workshop PDF):
  * 1 kWp of solar PV -> 901 kgCO2/year -> 0.901 carbon-credit unit/year
    (1 unit = 1 tonne CO2eq) and 101 trees/year. This is a *capacity-based*
    rule of thumb, independent of the degrading yearly generation - so it is
    deliberately computed differently from the scope-2 figure below, which is
    the physically-precise avoided-grid-emissions number (generation x EF).
  * Carbon market reference price = 100 baht / tonne CO2eq
        -> "CHAPTER 2: Carbon Credit" workshop PDF (reference-files/...)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# --- Tariff constants (baht per kWh, VAT excluded) -------------------------
# HV (>= 69 kV) selections confirmed by the user 2026-07-19.
NORMAL_TOU_HV_PEAK_THB_PER_KWH = 4.1025
UGT1_RETAIL_PREMIUM_THB_PER_KWH = 0.0375
UGT2_PORTFOLIO_A_HV_THB_PER_KWH = 4.0423

# The normal rate solar is valued at (daytime Peak, see module docstring).
NORMAL_RATE_THB_PER_KWH = NORMAL_TOU_HV_PEAK_THB_PER_KWH
# UGT1 = normal retail total (incl. Ft) + premium.
UGT1_RATE_THB_PER_KWH = NORMAL_RATE_THB_PER_KWH + UGT1_RETAIL_PREMIUM_THB_PER_KWH
UGT2_RATE_THB_PER_KWH = UGT2_PORTFOLIO_A_HV_THB_PER_KWH

# --- Carbon constants ------------------------------------------------------
# 0.4999 is the TGO grid-mix scope-2 factor from the reference files the user
# supplied on 2026-07-19. NOTE (2026-07-25): กกพ's own UGT criteria document
# quotes a DIFFERENT national figure - 0.4758 tCO2/MWh (and ~0.407 for 2565) -
# so two official Thai sources disagree. Which one this site should publish is
# the user's call, not a silent edit, so the default here is unchanged and the
# value was instead made user-settable (settings key
# `green.ef_scope2_kg_per_kwh`) with both figures named in its note.
EF_SCOPE2_KG_CO2_PER_KWH = 0.4999  # TGO grid-mix (scope 2)
CARBON_CREDIT_UNIT_PER_KWP_YEAR = 0.901  # tonne CO2eq / kWp / year (rule of thumb)
TREES_PER_KWP_YEAR = 101.0
CARBON_PRICE_THB_PER_TONNE = 100.0  # market reference price (workshop PDF)

@dataclass(frozen=True)
class GreenAssumptions:
    """The tariff/carbon constants above, overridable per call (2026-07-25).

    Every figure here is a published national rate or factor that changes on
    somebody else's schedule - a tariff announcement, a TGO/กกพ revision - so the
    user asked to be able to update them from the settings screen rather than
    waiting for a redeploy. Passed EXPLICITLY (the module keeps its constants as
    the defaults) so this stays a pure module: the route builds one from the
    effective settings and hands it in.
    """

    normal_rate_thb_per_kwh: float = NORMAL_RATE_THB_PER_KWH
    ugt1_premium_thb_per_kwh: float = UGT1_RETAIL_PREMIUM_THB_PER_KWH
    ugt2_rate_thb_per_kwh: float = UGT2_RATE_THB_PER_KWH
    ef_scope2_kg_per_kwh: float = EF_SCOPE2_KG_CO2_PER_KWH
    carbon_credit_unit_per_kwp_year: float = CARBON_CREDIT_UNIT_PER_KWP_YEAR
    trees_per_kwp_year: float = TREES_PER_KWP_YEAR
    carbon_price_thb_per_tonne: float = CARBON_PRICE_THB_PER_TONNE

    @property
    def ugt1_rate_thb_per_kwh(self) -> float:
        """UGT1 = the normal retail total (incl. Ft) + the premium - derived, not
        stored, so editing either input keeps the two consistent."""
        return self.normal_rate_thb_per_kwh + self.ugt1_premium_thb_per_kwh


DEFAULT_ASSUMPTIONS = GreenAssumptions()


# Human-readable labels for the assumptions footnote in the UI.
VOLTAGE_LEVEL_LABEL = "HV (≥ 69 kV)"
NORMAL_TARIFF_LABEL = "TOU – Peak (กิจการขนาดใหญ่ ประเภท 4)"
UGT2_PORTFOLIO_LABEL = "Portfolio A"


@dataclass(frozen=True)
class SavingsMetrics:
    """Every headline number for one (zone, horizon) cell of the table."""

    energy_kwh: float
    bill_saving_thb: float  # valued at the normal tariff
    ugt1_units_kwh: float  # avoided green-electricity purchase (= energy_kwh)
    ugt1_saving_thb: float
    ugt2_units_kwh: float  # = energy_kwh
    ugt2_saving_thb: float
    carbon_credit_units: float  # tonne CO2eq (capacity-based rule of thumb)
    carbon_credit_value_thb: float
    trees_equivalent: float
    scope2_co2_avoided_kg: float  # generation x EF (physically precise)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def compute_metrics(
    energy_kwh: float,
    dc_capacity_kwp: float,
    capacity_years: float,
    params: GreenAssumptions = DEFAULT_ASSUMPTIONS,
) -> SavingsMetrics:
    """One table cell.

    ``energy_kwh`` is the solar generation over the horizon (already carrying
    whatever degradation the caller baked in). ``capacity_years`` is the
    horizon expressed in years, used only for the *capacity-based* carbon
    credit / trees rule of thumb (e.g. 1/365 for a day, 25 for the lifetime) -
    those two are deliberately generation-independent per the user's rule.
    """
    if energy_kwh < 0:
        raise ValueError(f"energy_kwh cannot be negative, got {energy_kwh}")
    if dc_capacity_kwp < 0:
        raise ValueError(f"dc_capacity_kwp cannot be negative, got {dc_capacity_kwp}")

    carbon_credit_units = params.carbon_credit_unit_per_kwp_year * dc_capacity_kwp * capacity_years
    trees = params.trees_per_kwp_year * dc_capacity_kwp * capacity_years
    return SavingsMetrics(
        energy_kwh=energy_kwh,
        bill_saving_thb=energy_kwh * params.normal_rate_thb_per_kwh,
        ugt1_units_kwh=energy_kwh,
        ugt1_saving_thb=energy_kwh * params.ugt1_rate_thb_per_kwh,
        ugt2_units_kwh=energy_kwh,
        ugt2_saving_thb=energy_kwh * params.ugt2_rate_thb_per_kwh,
        carbon_credit_units=carbon_credit_units,
        carbon_credit_value_thb=carbon_credit_units * params.carbon_price_thb_per_tonne,
        trees_equivalent=trees,
        scope2_co2_avoided_kg=energy_kwh * params.ef_scope2_kg_per_kwh,
    )


def assumptions(params: GreenAssumptions = DEFAULT_ASSUMPTIONS) -> dict[str, float | str]:
    """The constants echoed to the UI so it can render a transparent footnote -
    the values actually in force, so an edited figure shows up in the footnote
    rather than the footnote still quoting the shipped default."""
    return {
        "voltage_level": VOLTAGE_LEVEL_LABEL,
        "normal_tariff": NORMAL_TARIFF_LABEL,
        "normal_rate_thb_per_kwh": params.normal_rate_thb_per_kwh,
        "ugt1_premium_thb_per_kwh": params.ugt1_premium_thb_per_kwh,
        "ugt1_rate_thb_per_kwh": params.ugt1_rate_thb_per_kwh,
        "ugt2_portfolio": UGT2_PORTFOLIO_LABEL,
        "ugt2_rate_thb_per_kwh": params.ugt2_rate_thb_per_kwh,
        "ef_scope2_kg_per_kwh": params.ef_scope2_kg_per_kwh,
        "carbon_credit_unit_per_kwp_year": params.carbon_credit_unit_per_kwp_year,
        "trees_per_kwp_year": params.trees_per_kwp_year,
        "carbon_price_thb_per_tonne": params.carbon_price_thb_per_tonne,
    }
