import { describe, expect, it } from 'vitest'
import {
  buildEnergyKpis,
  capacityFactorPct,
  facilityAnnualLoadKwh,
  formatEnergy,
  solarOffsetPct,
} from '../energyManagement'

describe('capacityFactorPct', () => {
  it('is energy / (rated power x 8760 h), in percent', () => {
    // 100 kW running flat-out all year = 100*8760 kWh -> 100%.
    expect(capacityFactorPct(100 * 8760, 100)).toBeCloseTo(100, 6)
    // Half that energy -> 50%.
    expect(capacityFactorPct(50 * 8760, 100)).toBeCloseTo(50, 6)
  })
  it('returns null for zero/negative capacity', () => {
    expect(capacityFactorPct(1000, 0)).toBeNull()
  })
})

describe('facilityAnnualLoadKwh / solarOffsetPct', () => {
  it('annual load is load x 8760', () => {
    expect(facilityAnnualLoadKwh(5000)).toBe(5000 * 8760)
  })
  it('offset is solar annual energy / facility annual demand, in percent', () => {
    const solar = 700_000 // kWh/yr
    const loadKw = 5000
    const expected = (solar / (5000 * 8760)) * 100
    expect(solarOffsetPct(solar, loadKw)).toBeCloseTo(expected, 6)
  })
  it('returns null when the (placeholder) facility load is missing/zero', () => {
    expect(solarOffsetPct(700_000, null)).toBeNull()
    expect(solarOffsetPct(700_000, 0)).toBeNull()
  })
})

describe('formatEnergy', () => {
  it('scales kWh -> MWh -> GWh', () => {
    expect(formatEnergy(500)).toMatch(/kWh$/)
    expect(formatEnergy(2_500)).toBe('2.5 MWh')
    expect(formatEnergy(3_400_000)).toBe('3.40 GWh')
  })
})

describe('buildEnergyKpis', () => {
  it('produces the standard KPI set with formatted values', () => {
    const kpis = buildEnergyKpis({
      annualAcEnergyKwh: 700_000,
      acCapacityKw: 200,
      performanceRatio: 0.84,
      specificYieldKwhPerKwp: 1500,
      co2SavedKgPerYear: 350_000,
    })
    const byKey = Object.fromEntries(kpis.map((k) => [k.key, k.value]))
    expect(byKey.performance_ratio).toBe('84.0%')
    expect(byKey.capacity_factor).toBe(`${((700_000 / (200 * 8760)) * 100).toFixed(1)}%`)
    expect(byKey.annual_energy).toBe('700.0 MWh')
    expect(byKey.specific_yield).toMatch(/1,500/)
  })
})
