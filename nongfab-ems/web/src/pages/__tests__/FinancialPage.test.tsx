import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../lib/api'
import { ApiError } from '../../lib/api'
import { AuthProvider } from '../../lib/auth'
import type { FinancialResponse } from '../../lib/types'
import { FinancialPage } from '../FinancialPage'

function makeFinancialResponse(overrides: Partial<FinancialResponse> = {}): FinancialResponse {
  return {
    installed_dc_capacity_kwp: 200.2,
    year_1_ac_energy_kwh: 250_000,
    capex_thb: 6_006_000,
    npv_thb: 1_500_000,
    irr_pct: 12.5,
    lcoe_thb_per_kwh: 2.1,
    simple_payback_years: 6.2,
    discounted_payback_years: 8.4,
    cash_flows: [
      {
        year: 1,
        ac_energy_kwh: 250_000,
        avoided_cost_thb: 1_000_000,
        opex_thb: 72_000,
        tax_thb: 185_600,
        net_cash_flow_thb: 742_400,
        cumulative_undiscounted_cash_flow_thb: -5_263_600,
        cumulative_discounted_cash_flow_thb: -5_318_222,
      },
    ],
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <FinancialPage />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('FinancialPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'postFinancial').mockResolvedValue(makeFinancialResponse())
  })

  it('runs an analysis automatically on mount with default (empty) assumptions', async () => {
    renderPage()
    await waitFor(() => expect(api.postFinancial).toHaveBeenCalledWith({}, expect.any(String)))
    expect(await screen.findByText('12.5')).toBeInTheDocument() // IRR
  })

  it('shows the placeholder-assumptions warning banner', async () => {
    renderPage()
    expect(screen.getByText(/documented placeholders/i)).toBeInTheDocument()
  })

  it('shows N/A for IRR and payback when the backend returns null (project never breaks even)', async () => {
    vi.spyOn(api, 'postFinancial').mockResolvedValue(
      makeFinancialResponse({ irr_pct: null, simple_payback_years: null, discounted_payback_years: null }),
    )
    renderPage()
    const naValues = await screen.findAllByText('N/A')
    expect(naValues.length).toBe(3)
  })

  it('toggling "use a known CAPEX figure" reveals a CAPEX input and includes it in the next request', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(api.postFinancial).toHaveBeenCalled())

    await user.click(screen.getByRole('checkbox', { name: /use a known capex figure/i }))
    const capexInput = screen.getByLabelText(/capex \(thb\)/i)
    await user.clear(capexInput)
    await user.type(capexInput, '9000000')

    await user.click(screen.getByRole('button', { name: /run analysis/i }))
    await waitFor(() =>
      expect(api.postFinancial).toHaveBeenLastCalledWith(expect.objectContaining({ capex_thb: 9_000_000 }), expect.any(String)),
    )
  })

  it('shows a role-specific message on a 403 (viewer running an operator-gated action)', async () => {
    vi.spyOn(api, 'postFinancial').mockRejectedValue(new ApiError(403, 'forbidden'))
    renderPage()
    expect(await screen.findByText(/operator or admin account/i)).toBeInTheDocument()
  })

  it('shows a generic error message on other failures', async () => {
    vi.spyOn(api, 'postFinancial').mockRejectedValue(new ApiError(422, 'invalid assumptions'))
    renderPage()
    expect(await screen.findByText(/financial analysis failed/i)).toBeInTheDocument()
  })
})
