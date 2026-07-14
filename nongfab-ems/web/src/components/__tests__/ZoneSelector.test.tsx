import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ZoneSelector } from '../ZoneSelector'
import { AuthProvider } from '../../lib/auth'
import * as api from '../../lib/api'
import type { AssetRegistry, Zone } from '../../lib/types'

function makeZone(id: string, simulated = false): Zone {
  return {
    id,
    name_full: id,
    ac_capacity_kw: 50,
    dc_capacity_kwp: 60,
    dc_ac_ratio: 1.2,
    module_count: 84,
    module_power_w: 715,
    inverter_model: 'SUN2000-50KTL-M3',
    inverter_count: 1,
    centroid: { lat: 12.68, lon: 101.12, elevation_m: null, note: null },
    simulated,
    module_detail: null,
    inverter_detail: null,
  }
}

const registry: AssetRegistry = { zones: [makeZone('GIS'), makeZone('ISB'), makeZone('Jetty', true)] }

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  )
}

describe('ZoneSelector', () => {
  beforeEach(() => {
    localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
  })

  it('renders All plus one tab per zone, flagging simulated zones', async () => {
    renderWithProviders(<ZoneSelector value="ALL" onChange={() => {}} />)

    expect(await screen.findByRole('tab', { name: /GIS/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /ISB/i })).toBeInTheDocument()
    const jettyTab = screen.getByRole('tab', { name: /Jetty/i })
    expect(jettyTab).toHaveTextContent(/sim/i)
    expect(screen.getByRole('tab', { name: /รวม/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('calls onChange with the clicked zone id', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<ZoneSelector value="ALL" onChange={onChange} />)

    await user.click(await screen.findByRole('tab', { name: /^GIS$/i }))
    expect(onChange).toHaveBeenCalledWith('GIS')
  })
})
