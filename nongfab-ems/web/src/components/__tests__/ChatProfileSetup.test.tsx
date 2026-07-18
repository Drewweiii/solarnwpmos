import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ChatProfileSetup } from '../ChatProfileSetup'

describe('ChatProfileSetup', () => {
  it('shows น้อง Solar (not an avatar) before anything is picked, for a brand-new profile', () => {
    render(<ChatProfileSetup initial={null} onSaved={vi.fn()} />)
    expect(screen.getByText(/น้อง Solar/)).toBeInTheDocument()
    // The mascot face SVG is present; no avatar preview span yet.
    expect(document.querySelector('.chat-profile-setup-avatar-preview')).not.toBeInTheDocument()
  })

  it('swaps the preview to the picked avatar as soon as one is clicked', async () => {
    const user = userEvent.setup()
    render(<ChatProfileSetup initial={null} onSaved={vi.fn()} />)

    await user.click(screen.getByRole('radio', { name: 'avatar fox' }))

    const preview = document.querySelector('.chat-profile-setup-avatar-preview')
    expect(preview).toBeInTheDocument()
    expect(preview).toHaveTextContent('🦊')
  })

  it('shows the current avatar preview immediately when editing an existing profile', () => {
    render(
      <ChatProfileSetup
        initial={{ clientId: 'c1', displayName: 'คนเดิม', avatarId: 'hamster' }}
        onSaved={vi.fn()}
      />,
    )
    const preview = document.querySelector('.chat-profile-setup-avatar-preview')
    expect(preview).toBeInTheDocument()
    expect(preview).toHaveTextContent('🐹')
  })

  it('picking a different avatar updates the live preview to match', async () => {
    const user = userEvent.setup()
    render(
      <ChatProfileSetup
        initial={{ clientId: 'c1', displayName: 'คนเดิม', avatarId: 'hamster' }}
        onSaved={vi.fn()}
      />,
    )
    expect(document.querySelector('.chat-profile-setup-avatar-preview')).toHaveTextContent('🐹')

    await user.click(screen.getByRole('radio', { name: 'avatar star' }))
    expect(document.querySelector('.chat-profile-setup-avatar-preview')).toHaveTextContent('⭐')
  })
})
