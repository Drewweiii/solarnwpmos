import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoginMascotDecor, moodFor } from '../LoginMascotDecor'

describe('moodFor', () => {
  it('watches (wide eyes) while the username field is focused', () => {
    expect(moodFor('username')).toBe('surprised')
  })

  it('looks away (closed eyes) while the password field is focused - never "peeking" at it', () => {
    expect(moodFor('password')).toBe('blush')
  })

  it('is idle when nothing is focused', () => {
    expect(moodFor(null)).toBe('idle')
  })
})

// Purely decorative (aria-hidden, no text/interactive content) - this
// guards against a render-time crash and confirms it stays out of the
// accessibility tree and reacts to `focusedField` via CSS state classes,
// not the rendered SVG shapes themselves (jsdom can't usefully assert on
// those - see mascotInteractions.test.ts's own precedent for this pattern).
describe('LoginMascotDecor', () => {
  it('renders as a single aria-hidden decoration with no interactive content', () => {
    const { container } = render(<LoginMascotDecor focusedField={null} />)
    const root = container.querySelector('.login-mascot-decor')
    expect(root).toBeInTheDocument()
    expect(root).toHaveAttribute('aria-hidden', 'true')
    expect(container.querySelectorAll('button, a, input')).toHaveLength(0)
  })

  it('renders all three characters (sun, moon, cloud)', () => {
    const { container } = render(<LoginMascotDecor focusedField={null} />)
    expect(container.querySelector('.login-mascot-sun')).toBeInTheDocument()
    expect(container.querySelector('.login-mascot-moon')).toBeInTheDocument()
    expect(container.querySelector('.login-mascot-cloud')).toBeInTheDocument()
  })

  it('adds a watching state class when the username field is focused', () => {
    const { container } = render(<LoginMascotDecor focusedField="username" />)
    expect(container.querySelector('.login-mascot-decor-watching')).toBeInTheDocument()
    expect(container.querySelector('.login-mascot-decor-shy')).not.toBeInTheDocument()
  })

  it('adds a shy (looking-away) state class when the password field is focused', () => {
    const { container } = render(<LoginMascotDecor focusedField="password" />)
    expect(container.querySelector('.login-mascot-decor-shy')).toBeInTheDocument()
    expect(container.querySelector('.login-mascot-decor-watching')).not.toBeInTheDocument()
  })

  it('adds neither state class when idle', () => {
    const { container } = render(<LoginMascotDecor focusedField={null} />)
    expect(container.querySelector('.login-mascot-decor-watching')).not.toBeInTheDocument()
    expect(container.querySelector('.login-mascot-decor-shy')).not.toBeInTheDocument()
  })
})
