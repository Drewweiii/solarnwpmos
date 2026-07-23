import { render } from '@testing-library/react'
import { createRef } from 'react'
import { describe, expect, it } from 'vitest'
import type { HandGesture, Landmark } from '../../lib/handControl'
import { HandPreview } from '../HandPreview'

function refs() {
  const videoRef = createRef<HTMLVideoElement | null>() as React.RefObject<HTMLVideoElement | null>
  const landmarksRef = { current: null as Landmark[] | null }
  const gestureRef = { current: 'control' as HandGesture }
  return { videoRef, landmarksRef, gestureRef }
}

describe('HandPreview', () => {
  it('renders nothing when inactive', () => {
    const { videoRef, landmarksRef, gestureRef } = refs()
    const { queryByTestId } = render(
      <HandPreview active={false} videoRef={videoRef} landmarksRef={landmarksRef} gestureRef={gestureRef} />,
    )
    expect(queryByTestId('hand-preview-canvas')).toBeNull()
  })

  it('renders a preview canvas when active without throwing (draw loop tolerates a null video)', () => {
    const { videoRef, landmarksRef, gestureRef } = refs()
    const { getByTestId } = render(
      <HandPreview active videoRef={videoRef} landmarksRef={landmarksRef} gestureRef={gestureRef} />,
    )
    expect(getByTestId('hand-preview-canvas')).toBeInstanceOf(HTMLCanvasElement)
  })
})
