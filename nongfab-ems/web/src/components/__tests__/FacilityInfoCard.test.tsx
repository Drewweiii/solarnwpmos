import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { LngTerminal } from '../../lib/types'
import { FacilityInfoCard } from '../FacilityInfoCard'

const terminal: LngTerminal = {
  official_name: 'Map Ta Phut LNG Terminal 2 (Nong Fab)',
  also_known_as: 'Nong Fab LNG Receiving Terminal (LMPT2)',
  is_thailand_second_onshore_terminal: true,
  owner: 'PTT LNG Company Limited (PTTLNG)',
  epc_contractors: 'Saipem + CTCI',
  owners_engineer: 'Artelia',
  location: 'Nong Fab, Mueang Rayong District, Rayong, Thailand',
  regas_capacity_mmtpa: 7.5,
  peak_capacity_mmtpa: 9,
  storage_tank_count: 2,
  storage_tank_capacity_m3: 250000,
  storage_tank_type: 'full-containment',
  storage_claim: 'largest LNG tank capacity ever executed in Thailand (per Saipem)',
  jetty_length_km_public: 5.5,
  jetty_length_km_user_stated: 5.66,
  trestle_length_km: 6,
  jetty_claim: "world's longest trestle in the LNG sector (per Saipem)",
  lng_carrier_min_m3: 125000,
  lng_carrier_max_m3: 266000,
  contract_awarded_year: 2018,
  epc_contract_value_musd: 925,
  investment_cost_billion_thb: 38.5,
  operational_since_year: 2022,
  first_cargo_date: '2022-06-18',
  first_cargo_carrier: 'Al Oraiq (210,100 m³ Q-Flex)',
  first_cargo_origin: 'Qatar (Qatargas)',
  land_area_total_ha: 29.7,
  land_area_terminal_ha: 21.6,
  land_area_office_ha: 8.1,
  cold_energy_reuse: true,
  seawater_recycling: true,
  landscape_award: 'Landezine International Landscape Award (LILA) - PTTLNG Receiving Terminal II',
  sources: ['https://example.com/a', 'https://example.com/b'],
}

describe('FacilityInfoCard', () => {
  it('renders nothing when there is no terminal data', () => {
    const { container } = render(<FacilityInfoCard terminal={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('is collapsed by default and expands the sourced facility facts on click', async () => {
    const user = userEvent.setup()
    render(<FacilityInfoCard terminal={terminal} />)
    const toggle = screen.getByRole('button', { name: /About this facility|เกี่ยวกับคลัง LNG/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // Body hidden until expanded.
    expect(screen.queryByText(/Map Ta Phut LNG Terminal 2/)).toBeNull()

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Map Ta Phut LNG Terminal 2/)).toBeInTheDocument()
    expect(screen.getByText(/7\.5 MMTPA/)).toBeInTheDocument()
    expect(screen.getByText(/250,000 m³/)).toBeInTheDocument()
    // Expanded Terminal-2 dataset is surfaced across the sections.
    expect(screen.getByText(/38\.5 พันล้านบาท/)).toBeInTheDocument() // investment
    expect(screen.getByText(/Al Oraiq/)).toBeInTheDocument() // first cargo
    expect(screen.getByText(/29\.7 เฮกตาร์/)).toBeInTheDocument() // land area
    expect(screen.getByText(/แห่งที่ 2 ของไทย/)).toBeInTheDocument() // 2nd-terminal badge
    // Honesty: the public-info disclaimer + source links are present.
    expect(screen.getByText(/ข้อมูลสาธารณะ/)).toBeInTheDocument()
    expect(screen.getAllByRole('link').length).toBe(2)
  })
})
