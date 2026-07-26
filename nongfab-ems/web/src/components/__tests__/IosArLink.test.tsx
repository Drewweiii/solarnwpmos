import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../../lib/auth'
import { arAvailability, isAppleTouchDevice, supportsArQuickLook, usdzScaleRatioLabel } from '../../lib/iosAr'
import { IosArLink } from '../IosArLink'

function renderLink() {
  localStorage.setItem('nongfab_ems_token', 'header.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.sig')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <IosArLink zone="GIS" sceneSpan={240} />
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('AR Quick Look link', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('holds exactly one child element, and it is an img', () => {
    // Apple's requirement, and the single most consequential detail here: with
    // any other content Safari stops treating this as an AR link and just
    // navigates to the .usdz, downloading a file the viewer cannot open.
    renderLink()
    const anchor = screen.getByRole('link')
    expect(anchor.children).toHaveLength(1)
    expect(anchor.children[0].tagName).toBe('IMG')
  })

  it('marks the link rel="ar" and points at the zone usdz', () => {
    renderLink()
    const anchor = screen.getByRole('link')
    expect(anchor).toHaveAttribute('rel', 'ar')
    expect(anchor.getAttribute('href')).toContain('/ar/GIS.usdz')
  })

  it('carries the token in the query string', () => {
    // Quick Look fetches the URL outside the page and cannot send an
    // Authorization header - the same constraint the chat WebSocket has.
    renderLink()
    expect(screen.getByRole('link').getAttribute('href')).toContain('token=')
  })

  it('states the scale, because a tabletop model implies its own size', () => {
    renderLink()
    expect(screen.getByText(/1 : 400/)).toBeInTheDocument()
    expect(screen.getByText(/ไม่ใช่ขนาดจริง/)).toBeInTheDocument()
  })

  it('renders nothing without a token rather than a broken link', () => {
    const client = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <IosArLink zone="GIS" sceneSpan={240} />
        </AuthProvider>
      </QueryClientProvider>,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('iOS AR detection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('answers false instead of throwing where rel="ar" is unknown', () => {
    // DOMTokenList.supports() is specified to THROW when the attribute has no
    // supported-tokens definition, which is the case for anchor `rel` in every
    // engine without Quick Look. Unguarded this took the page down under jsdom,
    // and would have done the same on Firefox.
    expect(() => supportsArQuickLook()).not.toThrow()
    expect(supportsArQuickLook()).toBe(false)
    expect(arAvailability()).toBe('not-apple')
  })

  it('recognises an iPad that reports itself as a Mac', () => {
    // Since iPadOS 13 an iPad claims platform MacIntel; touch points are the
    // only thing separating it from a desktop, and without this clause every
    // iPad would be told AR is unavailable for the wrong reason.
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 5 })
    expect(isAppleTouchDevice()).toBe(true)
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 0 })
    expect(isAppleTouchDevice()).toBe(false)
  })

  it('recognises an iPhone from its user agent', () => {
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)', platform: 'iPhone', maxTouchPoints: 5 })
    expect(isAppleTouchDevice()).toBe(true)
  })

  it('labels the scale the same way the WebXR path does', () => {
    expect(usdzScaleRatioLabel(240)).toBe('1 : 400')
    expect(usdzScaleRatioLabel(0.3)).toBe('1 : 1')
    expect(usdzScaleRatioLabel(0)).toBe('1 : 1')
  })
})
