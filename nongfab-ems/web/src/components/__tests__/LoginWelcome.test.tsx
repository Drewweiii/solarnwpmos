import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { LoginWelcome } from '../LoginWelcome'

describe('LoginWelcome', () => {
  it('shows up automatically greeting the visitor as น้อง Solar, with the viewer login credentials', () => {
    render(<LoginWelcome />)
    expect(screen.getByRole('dialog', { name: /น้อง Solar/ })).toBeInTheDocument()
    expect(screen.getByText(/pttlng/)).toBeInTheDocument()
    expect(screen.getByText(/12345/)).toBeInTheDocument()
  })

  it('can be dismissed with the close button', async () => {
    const user = userEvent.setup()
    render(<LoginWelcome />)
    await user.click(screen.getByRole('button', { name: 'ปิดหน้าต่างแนะนำ' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('can be dismissed with the "understood" call-to-action button', async () => {
    const user = userEvent.setup()
    render(<LoginWelcome />)
    await user.click(screen.getByRole('button', { name: 'เข้าใจแล้ว เริ่มใช้งานเลย' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('can be dismissed by clicking the backdrop, but not by clicking inside the card', async () => {
    const user = userEvent.setup()
    render(<LoginWelcome />)
    await user.click(screen.getByText(/ผมชื่อ "น้อง Solar"/))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('dialog').parentElement!)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
