import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FinancialUncertainty, MetricPercentiles } from '../../lib/types'
import { FinancialUncertaintyPanel, orientBand } from '../FinancialUncertaintyPanel'

function metric(name: string, p10: number | null, p50: number | null, p90: number | null, undefined_trials = 0): MetricPercentiles {
  return { metric: name, p10, p50, p90, mean: p50, undefined_trials }
}

function makeUncertainty(overrides: Partial<FinancialUncertainty> = {}): FinancialUncertainty {
  return {
    available: true,
    reason: null,
    // Real figures from the installed GIS+ISB array, 2026-07-25. The P90 is the
    // narrower band that came out of the DERIVED 2.11% interannual CV (26 years
    // of NASA POWER at this site) rather than the 4% literature guess it
    // replaced - that change halved the shortfall, so it belongs in the fixture.
    yield_levels: [
      { label: 'P50', exceedance: 0.5, annual_energy_kwh: 377_081 },
      { label: 'P90', exceedance: 0.9, annual_energy_kwh: 366_884 },
    ],
    samples: 2000,
    metrics: [
      metric('npv_thb', 7_502_594, 10_785_708, 14_842_378),
      metric('irr_pct', 20.57, 25.3, 31.74),
      metric('simple_payback_years', 3.22, 4.02, 4.89),
      metric('lcoe_thb_per_kwh', 1.43, 1.81, 2.24),
    ],
    probability_npv_negative_pct: 0,
    probability_no_payback_pct: 0,
    method_note: 'ตัวเลขชุดนี้บอกความไม่แน่ใจ ไม่ใช่ความแปรปรวนที่วัดได้',
    ...overrides,
  }
}

describe('orientBand', () => {
  it('for NPV (higher is better) the pessimistic end is P10', () => {
    const band = orientBand(metric('npv_thb', 1, 5, 9), false)
    expect(band).toEqual({ bad: 1, mid: 5, good: 9 })
  })

  it('for payback (LOWER is better) the pessimistic end is P90, not P10', () => {
    // The whole reason this helper exists: presenting 3.2 years as the "bad"
    // case and 4.9 as the "good" one would invert the reader's conclusion.
    const band = orientBand(metric('simple_payback_years', 3.22, 4.02, 4.89), true)
    expect(band).toEqual({ bad: 4.89, mid: 4.02, good: 3.22 })
  })

  it('carries nulls through rather than substituting a number', () => {
    expect(orientBand(metric('simple_payback_years', null, null, null), true)).toEqual({
      bad: null,
      mid: null,
      good: null,
    })
  })
})

describe('FinancialUncertaintyPanel', () => {
  it('renders nothing when the API sent no uncertainty block at all', () => {
    const { container } = render(<FinancialUncertaintyPanel uncertainty={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows P90 below P50 and explains what each means', () => {
    render(<FinancialUncertaintyPanel uncertainty={makeUncertainty()} />)
    expect(screen.getByText('377,081 kWh')).toBeInTheDocument()
    expect(screen.getByText('366,884 kWh')).toBeInTheDocument()
    expect(screen.getByText(/90% ของปีจะทำได้เกิน/)).toBeInTheDocument()
  })

  it('reports the P50-to-P90 shortfall a lender would underwrite on', () => {
    render(<FinancialUncertaintyPanel uncertainty={makeUncertainty()} />)
    expect(screen.getByText(/10,197 kWh\/ปี/)).toBeInTheDocument()
  })

  it('puts the LONGER payback in the bad column and the shorter in the good one', () => {
    render(<FinancialUncertaintyPanel uncertainty={makeUncertainty()} />)
    const row = screen.getByText(/ระยะคืนทุน/).closest('tr')!
    const cells = within(row).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('4.89') // bad
    expect(cells[2]).toHaveTextContent('4.02') // mid
    expect(cells[3]).toHaveTextContent('3.22') // good
  })

  it('puts the LOWER NPV in the bad column - the opposite direction', () => {
    render(<FinancialUncertaintyPanel uncertainty={makeUncertainty()} />)
    // /NPV/ alone also matches the 'NPV ติดลบ' risk sentence below the table.
    const row = screen.getByText(/NPV \(มูลค่าปัจจุบันสุทธิ\)/).closest('tr')!
    const cells = within(row).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('7,502,594')
    expect(cells[3]).toHaveTextContent('14,842,378')
  })

  it('surfaces the chance of losing money and of never paying back', () => {
    render(
      <FinancialUncertaintyPanel
        uncertainty={makeUncertainty({ probability_npv_negative_pct: 12.5, probability_no_payback_pct: 4.25 })}
      />,
    )
    expect(screen.getByText('12.5%')).toBeInTheDocument()
    expect(screen.getByText('4.25%')).toBeInTheDocument()
  })

  it('flags trials where a metric was undefined instead of hiding them', () => {
    render(
      <FinancialUncertaintyPanel
        uncertainty={makeUncertainty({
          metrics: [metric('simple_payback_years', 3.2, 4.0, 4.9, 240)],
        })}
      />,
    )
    expect(screen.getByText(/240 รอบไม่นิยาม/)).toBeInTheDocument()
  })

  it('shows an em dash, not a zero, for a metric undefined in every trial', () => {
    // "never paid back" must not read as "paid back at year 0".
    render(
      <FinancialUncertaintyPanel
        uncertainty={makeUncertainty({ metrics: [metric('simple_payback_years', null, null, null, 2000)] })}
      />,
    )
    const row = screen.getByText(/ระยะคืนทุน/).closest('tr')!
    const cells = within(row).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('—')
    expect(cells[2]).toHaveTextContent('—')
    expect(cells[3]).toHaveTextContent('—')
  })

  it('explains itself as assumption uncertainty, not measured variability', () => {
    render(<FinancialUncertaintyPanel uncertainty={makeUncertainty()} />)
    expect(screen.getByText(/ไม่ใช่ความแปรปรวนที่วัดได้/)).toBeInTheDocument()
  })

  it('says so plainly when no uncertainty has been configured', () => {
    render(
      <FinancialUncertaintyPanel
        uncertainty={makeUncertainty({ available: false, reason: 'ยังไม่ได้ตั้งค่าความไม่แน่นอนของสมมติฐานใดเลย' })}
      />,
    )
    expect(screen.getByText(/ยังไม่ได้ตั้งค่าความไม่แน่นอน/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
