// Pure energy-management KPI calculations (2026-07-23). Kept free of React/DOM
// so they're fully unit-testable. Everything here is derived from figures the
// Energy Report / assets registry already provide - no new data source - except
// the facility-load offset, which depends on a documented PLACEHOLDER load (see
// config/assets.yaml site.facility_electrical_load_kw) and is therefore always
// surfaced with an "assumption" caveat in the UI.

const HOURS_PER_YEAR = 8760

/** Capacity factor (%) = actual annual energy / (rated AC power x hours in a
 * year). The share of nameplate the plant actually delivers over a year - a
 * standard EMS headline KPI. Returns null when capacity is unknown/zero. */
export function capacityFactorPct(annualAcEnergyKwh: number, acCapacityKw: number): number | null {
  if (acCapacityKw <= 0) return null
  return (annualAcEnergyKwh / (acCapacityKw * HOURS_PER_YEAR)) * 100
}

/** A rough facility annual electricity demand (kWh) from a constant load (kW).
 * Deliberately simple (flat load x hours) because the input is already a
 * placeholder - a fancier load profile would imply a precision we don't have. */
export function facilityAnnualLoadKwh(facilityLoadKw: number): number {
  return facilityLoadKw * HOURS_PER_YEAR
}

/** Solar self-supply / offset (%) = annual solar energy / facility annual
 * demand. How much of the terminal's own electricity the array could cover.
 * Returns null when the (placeholder) facility load is unknown/zero. */
export function solarOffsetPct(annualAcEnergyKwh: number, facilityLoadKw: number | null | undefined): number | null {
  if (facilityLoadKw == null || facilityLoadKw <= 0) return null
  return (annualAcEnergyKwh / facilityAnnualLoadKwh(facilityLoadKw)) * 100
}

/** The facility's implied average electricity tariff (THB/kWh) = annual cost /
 * annual load energy. Both inputs are user-stated real figures, so this is an
 * internally-consistent blended rate, not a published tariff. Returns null when
 * either input is missing/zero. */
export function impliedTariffThbPerKwh(
  annualCostThb: number | null | undefined,
  facilityLoadKw: number | null | undefined,
): number | null {
  if (annualCostThb == null || annualCostThb <= 0) return null
  if (facilityLoadKw == null || facilityLoadKw <= 0) return null
  return annualCostThb / facilityAnnualLoadKwh(facilityLoadKw)
}

/** Approximate annual bill saving (THB) from the solar output, valuing each
 * solar kWh at the facility's own implied average tariff. Returns null when the
 * tariff can't be derived. */
export function solarBillSavingThbPerYear(
  annualAcEnergyKwh: number,
  annualCostThb: number | null | undefined,
  facilityLoadKw: number | null | undefined,
): number | null {
  const tariff = impliedTariffThbPerKwh(annualCostThb, facilityLoadKw)
  if (tariff == null) return null
  return annualAcEnergyKwh * tariff
}

/** That bill saving as a % of the facility's total annual electricity cost. */
export function solarBillSavingPct(
  annualAcEnergyKwh: number,
  annualCostThb: number | null | undefined,
  facilityLoadKw: number | null | undefined,
): number | null {
  const saving = solarBillSavingThbPerYear(annualAcEnergyKwh, annualCostThb, facilityLoadKw)
  if (saving == null || annualCostThb == null || annualCostThb <= 0) return null
  return (saving / annualCostThb) * 100
}

/** Format a THB figure into a compact ฿ / พัน / ล้าน string (Thai scale). */
export function formatThb(thb: number): string {
  if (thb >= 1_000_000) return `${(thb / 1_000_000).toFixed(2)} ล้านบาท`
  if (thb >= 1_000) return `${(thb / 1_000).toFixed(0)} พันบาท`
  return `${Math.round(thb).toLocaleString('en-US')} บาท`
}

export interface EnergyKpi {
  key: string
  label: string
  value: string
  hint?: string
}

/** Format a kWh figure into a compact kWh / MWh / GWh string. */
export function formatEnergy(kwh: number): string {
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toFixed(2)} GWh`
  if (kwh >= 1_000) return `${(kwh / 1_000).toFixed(1)} MWh`
  return `${Math.round(kwh).toLocaleString('en-US')} kWh`
}

export interface BuildKpisInput {
  annualAcEnergyKwh: number
  acCapacityKw: number
  performanceRatio: number // 0..1
  specificYieldKwhPerKwp: number // annual
  co2SavedKgPerYear: number
}

/** Assemble the standard EMS KPI set for the panel. Pure so it's testable. */
export function buildEnergyKpis(input: BuildKpisInput): EnergyKpi[] {
  const cf = capacityFactorPct(input.annualAcEnergyKwh, input.acCapacityKw)
  return [
    {
      key: 'annual_energy',
      label: 'พลังงานผลิตต่อปี (Annual energy)',
      value: formatEnergy(input.annualAcEnergyKwh),
    },
    {
      key: 'performance_ratio',
      label: 'Performance Ratio (PR)',
      value: `${(input.performanceRatio * 100).toFixed(1)}%`,
      hint: 'สัดส่วนพลังงานจริงต่อพลังงานตามทฤษฎี',
    },
    {
      key: 'specific_yield',
      label: 'Specific Yield',
      value: `${Math.round(input.specificYieldKwhPerKwp).toLocaleString('en-US')} kWh/kWp/ปี`,
      hint: 'พลังงานต่อกำลังติดตั้ง 1 kWp',
    },
    {
      key: 'capacity_factor',
      label: 'Capacity Factor',
      value: cf == null ? '—' : `${cf.toFixed(1)}%`,
      hint: 'สัดส่วนพลังงานจริงต่อกำลังพิกัดเต็มปี',
    },
    {
      key: 'co2',
      label: 'CO₂ ที่ลดได้ต่อปี',
      value: `${Math.round(input.co2SavedKgPerYear).toLocaleString('en-US')} kg`,
    },
  ]
}
