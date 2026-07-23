import { describe, expect, it } from 'vitest'
import {
  buildEnergyKpis,
  capacityFactorPct,
  facilityAnnualLoadKwh,
  formatEnergy,
  formatThb,
  impliedTariffThbPerKwh,
  solarBillSavingPct,
  solarBillSavingThbPerYear,
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

describe('implied tariff + bill saving (real user-stated facility figures)', () => {
  const cost = 300_000_000 // THB/yr
  const loadKw = 13500 // 13.5 MW

  it('implied tariff = annual cost / annual load energy', () => {
    const t = impliedTariffThbPerKwh(cost, loadKw)
    expect(t).toBeCloseTo(cost / (13500 * 8760), 9) // ~2.54 THB/kWh
  })

  it('bill saving = solar annual energy x implied tariff, and its % of total cost', () => {
    const solar = 700_000
    const tariff = cost / (13500 * 8760)
    expect(solarBillSavingThbPerYear(solar, cost, loadKw)).toBeCloseTo(solar * tariff, 3)
    expect(solarBillSavingPct(solar, cost, loadKw)).toBeCloseTo(((solar * tariff) / cost) * 100, 6)
  })

  it('returns null when the cost or load is missing', () => {
    expect(impliedTariffThbPerKwh(null, loadKw)).toBeNull()
    expect(solarBillSavingThbPerYear(700_000, cost, null)).toBeNull()
    expect(solarBillSavingPct(700_000, null, loadKw)).toBeNull()
  })
})

describe('formatThb', () => {
  it('scales THB -> พันบาท -> ล้านบาท', () => {
    expect(formatThb(500)).toMatch(/บาท$/)
    expect(formatThb(12_000)).toBe('12 พันบาท')
    expect(formatThb(1_780_000)).toBe('1.78 ล้านบาท')
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
