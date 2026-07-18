import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OrgLogos } from '../OrgLogos'

describe('OrgLogos', () => {
  it('renders the site logo plus all 5 partner organization logos', () => {
    render(<OrgLogos variant="footer" />)
    expect(screen.getByAltText('PTT LNG Terminal 2 Nong Fab Solar Forecasting')).toBeInTheDocument()
    expect(screen.getByAltText('PTT LNG')).toBeInTheDocument()
    expect(screen.getByAltText('PE LNG Co., Ltd.')).toBeInTheDocument()
    expect(screen.getByAltText('Electrical Engineering, Chulalongkorn University')).toBeInTheDocument()
    expect(screen.getByAltText('Chula Engineering - Innovation toward Sustainability')).toBeInTheDocument()
    expect(screen.getByAltText('Chulalongkorn University')).toBeInTheDocument()
  })

  it('applies a distinct class per variant so login/footer can be styled differently', () => {
    const { container: loginContainer } = render(<OrgLogos variant="login" />)
    expect(loginContainer.querySelector('.org-logos-login')).toBeInTheDocument()

    const { container: footerContainer } = render(<OrgLogos variant="footer" />)
    expect(footerContainer.querySelector('.org-logos-footer')).toBeInTheDocument()
  })
})
