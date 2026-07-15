import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { SLDData } from '../../lib/types'
import { SLDViewer } from '../SLDViewer'

const sld: SLDData = {
  module_model: 'Trina Vertex N TSM-NEG21C.20',
  module_power_w: 715,
  optimizer_model: 'Huawei MERC-1300W-P',
  optimizer_ratio_modules_per_optimizer: 2,
  approximate_string_distribution: true,
  blocks: [
    {
      id: 'INV-1',
      inverter_model: 'SUN2000-50KTL-M3',
      inverter_ac_kw: 50,
      mppt_count: 4,
      strings: [
        { id: 'ST-1', modules: 21 },
        { id: 'ST-2', modules: 21 },
        { id: 'ST-3', modules: 21 },
        { id: 'ST-4', modules: 21 },
      ],
    },
  ],
}

describe('SLDViewer', () => {
  it('renders every block and string as clickable nodes', () => {
    render(<SLDViewer sld={sld} />)
    expect(screen.getByText('INV-1')).toBeInTheDocument()
    expect(screen.getByText('ST-1')).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(5) // 4 strings + 1 inverter
  })

  it('shows a hint before anything is selected', () => {
    render(<SLDViewer sld={sld} />)
    expect(screen.getByText(/click a string or inverter/i)).toBeInTheDocument()
  })

  it('clicking a string shows its module count and module model', async () => {
    const user = userEvent.setup()
    render(<SLDViewer sld={sld} />)
    await user.click(screen.getByText('ST-1'))
    expect(screen.getByText(/21 x 715 W/)).toBeInTheDocument()
    expect(screen.getByText('Trina Vertex N TSM-NEG21C.20')).toBeInTheDocument()
  })

  it('clicking the inverter block shows its AC rating and MPPT count', async () => {
    const user = userEvent.setup()
    render(<SLDViewer sld={sld} />)
    await user.click(screen.getByText('INV-1'))
    expect(screen.getAllByText('50 kW').length).toBeGreaterThan(0)
    expect(screen.getByText('MPPT inputs').nextElementSibling).toHaveTextContent('4')
  })

  it('shows the approximation note only when flagged', () => {
    const { rerender } = render(<SLDViewer sld={sld} />)
    expect(screen.getByText(/even-split approximation/i)).toBeInTheDocument()

    rerender(<SLDViewer sld={{ ...sld, approximate_string_distribution: false }} />)
    expect(screen.queryByText(/even-split approximation/i)).not.toBeInTheDocument()
  })
})
