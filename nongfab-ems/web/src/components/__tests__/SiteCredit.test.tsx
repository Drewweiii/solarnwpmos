import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SiteCredit } from '../SiteCredit'

describe('SiteCredit', () => {
  it('renders nothing while the real credit text is still blank', () => {
    const { container } = render(<SiteCredit text="" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the credit text once one is provided', () => {
    render(<SiteCredit text="พัฒนาโดยทีม Nong Fab Solar EMS" />)
    expect(screen.getByText('พัฒนาโดยทีม Nong Fab Solar EMS')).toBeInTheDocument()
  })
})
