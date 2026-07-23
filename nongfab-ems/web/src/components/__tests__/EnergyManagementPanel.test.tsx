import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { EnergyReportResponse } from '../../lib/types'
import { EnergyManagementPanel } from '../EnergyManagementPanel'

function makeReport(): EnergyReportResponse {
  return {
    zone: 'GIS',
    simulated_zone: false,
    system_summary: {
      ac_capacity_kw: 200,
      dc_capacity_kwp: 228.8,
      dc_ac_ratio: 1.14,
      module_count: 320,
      module_power_w: 715,
      array_area_m2: 1000,
      inverter_model: 'SUN2000-50KTL-M3',
      inverter_count: 4,
    },
    annual: { ac_energy_kwh: 700_000, specific_yield_kwh_per_kwp: 1500, performance_ratio: 0.84 },
    loss_breakdown_pct: {},
    co2_saved_kg_per_year: 350_000,
    trees_equivalent_per_year: 3500,
    avg_solar_access_pct: 95,
    monthly: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, ac_energy_kwh: 58_000, is_rainy_season: false })),
    lifecycle: {
      year_1_ac_energy_kwh: 700_000,
      year_25_ac_energy_kwh: 600_000,
      year_25_pct_of_year_1: 85,
      lifetime_ac_energy_kwh: 16_000_000,
      degradation_pct_per_year_assumed: 0.5,
    },
    sld: { module_model: null, module_power_w: 715, optimizer_model: null, optimizer_ratio_modules_per_optimizer: null, blocks: [], approximate_string_distribution: false },
  }
}

describe('EnergyManagementPanel', () => {
  it('renders the KPI strip, PPA code and a solar-offset % when a facility load is given', () => {
    render(<EnergyManagementPanel report={makeReport()} facilityLoadKw={5000} ppaCode="PPA25_0008" />)
    expect(screen.getByText(/Energy Management/)).toBeInTheDocument()
    expect(screen.getByText('84.0%')).toBeInTheDocument() // PR
    // offset = 700000 / (5000*8760) *100 ~= 1.6%
    expect(screen.getByText(/1\.6%/)).toBeInTheDocument()
    expect(screen.getByText(/PPA: PPA25_0008/)).toBeInTheDocument()
    // The placeholder caveat must be shown, never presented as measured.
    expect(screen.getByText(/placeholder/i)).toBeInTheDocument()
  })

  it('states the load is missing (no fabricated offset) when facility load is null', () => {
    render(<EnergyManagementPanel report={makeReport()} facilityLoadKw={null} />)
    expect(screen.getByText(/ยังไม่มีค่าโหลดไฟฟ้าของคลัง/)).toBeInTheDocument()
  })
})
