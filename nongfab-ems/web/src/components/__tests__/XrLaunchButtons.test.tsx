import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { XrLaunchButtons } from '../XrLaunchButtons'

afterEach(() => {
  delete (navigator as unknown as Record<string, unknown>).xr
})

function withXr(supported: (mode: string) => boolean) {
  ;(navigator as unknown as Record<string, unknown>).xr = {
    isSessionSupported: async (mode: string) => supported(mode),
  }
}

describe('XrLaunchButtons', () => {
  it('renders nothing at all where WebXR is absent - iPhone, plain desktop', async () => {
    // A button that does nothing on the device half the audience is holding
    // would be worse than no button.
    const { container } = render(<XrLaunchButtons sceneSpan={240} />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('offers only the mode the device actually supports', async () => {
    withXr((mode) => mode === 'immersive-vr')
    render(<XrLaunchButtons sceneSpan={240} />)
    expect(await screen.findByText(/ดูแบบ VR/)).toBeInTheDocument()
    expect(screen.queryByText(/ดูแบบ AR/)).not.toBeInTheDocument()
  })

  it('offers both on a device that does both', async () => {
    withXr(() => true)
    render(<XrLaunchButtons sceneSpan={240} />)
    expect(await screen.findByText(/ดูแบบ AR/)).toBeInTheDocument()
    expect(screen.getByText(/ดูแบบ VR/)).toBeInTheDocument()
  })

  it('states the scale, so the tabletop model is not read as life-size', async () => {
    withXr(() => true)
    render(<XrLaunchButtons sceneSpan={240} />)
    expect(await screen.findByText(/1 : 400/)).toBeInTheDocument()
    expect(screen.getByText(/ไม่ใช่ขนาดจริง/)).toBeInTheDocument()
  })
})
