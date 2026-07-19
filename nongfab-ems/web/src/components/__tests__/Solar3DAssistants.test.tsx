import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Solar3DAssistants } from '../Solar3DAssistants'

/** The Moon/Cloud "buddy" that pops up next to น้อง Solar is decorative
 * (aria-hidden), so we assert on its DOM class rather than a role - the
 * persona-suffixed class is what drives the CSS pop-up + idle animation, and
 * swapping it (via a React key) is what re-triggers the pop. */
function buddy(container: HTMLElement, persona: 'moon' | 'cloud') {
  return container.querySelector(`.solar3d-assistant-buddy-${persona}`)
}

describe('Solar3DAssistants pop-up buddy', () => {
  it('shows no buddy until a launcher is tapped', () => {
    const { container } = render(<Solar3DAssistants />)
    expect(container.querySelector('.solar3d-assistant-buddy')).toBeNull()
  })

  it('pops the Moon buddy in when the Moon launcher is tapped', async () => {
    const { container } = render(<Solar3DAssistants />)
    await userEvent.click(screen.getByRole('button', { name: /น้อง Moon/ }))
    expect(buddy(container, 'moon')).not.toBeNull()
    expect(buddy(container, 'cloud')).toBeNull()
  })

  it('swaps the buddy to Cloud when the Cloud launcher is tapped', async () => {
    const { container } = render(<Solar3DAssistants />)
    await userEvent.click(screen.getByRole('button', { name: /น้อง Moon/ }))
    await userEvent.click(screen.getByRole('button', { name: /น้อง Cloud/ }))
    expect(buddy(container, 'cloud')).not.toBeNull()
    expect(buddy(container, 'moon')).toBeNull()
  })

  it('dismisses the buddy when the active launcher is tapped again', async () => {
    const { container } = render(<Solar3DAssistants />)
    const moon = screen.getByRole('button', { name: /น้อง Moon/ })
    await userEvent.click(moon)
    expect(container.querySelector('.solar3d-assistant-buddy')).not.toBeNull()
    await userEvent.click(moon)
    expect(container.querySelector('.solar3d-assistant-buddy')).toBeNull()
  })
})
