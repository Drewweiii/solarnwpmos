import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Compass } from '../Compass'

describe('Compass', () => {
  it('renders the rounded azimuth, compass label, and altitude', () => {
    render(<Compass azimuthDeg={206} elevationDeg={38} />)
    expect(screen.getByText(/206.*SW/)).toBeInTheDocument()
    expect(screen.getByText(/Alt: 38/)).toBeInTheDocument()
  })

  it('exposes an accessible label with the raw values', () => {
    render(<Compass azimuthDeg={90} elevationDeg={45} />)
    expect(screen.getByRole('img', { name: /azimuth 90 degrees, altitude 45 degrees/i })).toBeInTheDocument()
  })
})
