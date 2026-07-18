import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoginSolarDecor } from '../LoginSolarDecor'

// Purely decorative (aria-hidden, no text/interactive content) - this just
// guards against a render-time crash and confirms it stays out of the
// accessibility tree, not visual details CSS already covers.
describe('LoginSolarDecor', () => {
  it('renders as a single aria-hidden decoration with no interactive content', () => {
    const { container } = render(<LoginSolarDecor />)
    const root = container.querySelector('.login-solar-decor')
    expect(root).toBeInTheDocument()
    expect(root).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelectorAll('button, a, input')).toHaveLength(0)
  })
})
