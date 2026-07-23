import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { LngTerminal } from '../../lib/types'
import { FacilityInfoCard } from '../FacilityInfoCard'

const terminal: LngTerminal = {
  official_name: 'Map Ta Phut LNG Terminal 2 (Nong Fab)',
  owner: 'PTT LNG Company Limited (PTTLNG)',
  epc_contractors: 'Saipem + CTCI',
  operational_since_year: 2022,
  regas_capacity_mmtpa: 7.5,
  peak_capacity_mmtpa: 9,
  storage_tank_count: 2,
  storage_tank_capacity_m3: 250000,
  storage_tank_type: 'full-containment',
  jetty_length_km_public: 5.5,
  jetty_length_km_user_stated: 5.66,
  lng_carrier_min_m3: 125000,
  lng_carrier_max_m3: 266000,
  cold_energy_reuse: true,
  seawater_recycling: true,
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
    // Honesty: the public-info disclaimer + source links are present.
    expect(screen.getByText(/ข้อมูลสาธารณะ/)).toBeInTheDocument()
    expect(screen.getAllByRole('link').length).toBe(2)
  })
})
