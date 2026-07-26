import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ForecastKpiBlock } from '../ForecastKpiBlock'
import type { ForecastPoint } from '../../lib/types'

const NOW = '2026-07-25T05:00:00Z' // 12:00 ICT on the 25th

function point(timestamp: string, pred: number, lower: number | null = null, upper: number | null = null): ForecastPoint {
  return { timestamp, pred, lower, upper, algorithm: 'neuralprophet', error: null, candidate_errors: null }
}

// 06:00-18:00 ICT on the 26th, peaking at 12:00 ICT (05:00Z).
const tomorrow: ForecastPoint[] = [
  point('2026-07-25T23:00:00Z', 12, 8, 16),
  point('2026-07-26T02:00:00Z', 90, 70, 110),
  point('2026-07-26T05:00:00Z', 150, 120, 180),
  point('2026-07-26T08:00:00Z', 60, 40, 80),
  point('2026-07-26T11:00:00Z', 0),
]

describe('ForecastKpiBlock', () => {
  it('reports tomorrow energy, peak and peak time on the day-ahead tab', () => {
    render(<ForecastKpiBlock points={tomorrow} horizon="day" isLoading={false} hasError={false} nowIso={NOW} />)
    // 5 points, 3-hour spacing -> (12+90+150+60+0) * 3 = 936 kWh
    expect(screen.getByText('936')).toBeInTheDocument()
    expect(screen.getByText('150')).toBeInTheDocument()
    expect(screen.getByText(/12:00/)).toBeInTheDocument()
  })

  it('shows the interval at the peak as a percentage', () => {
    render(<ForecastKpiBlock points={tomorrow} horizon="day" isLoading={false} hasError={false} nowIso={NOW} />)
    // (180-120)/2 = 30 kW on a 150 kW peak = 20%
    expect(screen.getByText('±20%')).toBeInTheDocument()
  })

  it('says the physics fallback has no interval instead of rendering it as zero', () => {
    const noBand = [point('2026-07-26T05:00:00Z', 150)]
    render(<ForecastKpiBlock points={noBand} horizon="day" isLoading={false} hasError={false} nowIso={NOW} />)
    expect(screen.getByText(/ไม่ได้ให้ช่วงความเชื่อมั่น/)).toBeInTheDocument()
  })

  it('switches window with the horizon toggle', () => {
    const { rerender } = render(
      <ForecastKpiBlock points={tomorrow} horizon="day" isLoading={false} hasError={false} nowIso={NOW} />,
    )
    expect(screen.getByText(/พรุ่งนี้ทั้งวัน/)).toBeInTheDocument()

    rerender(<ForecastKpiBlock points={tomorrow} horizon="hour" isLoading={false} hasError={false} nowIso={NOW} />)
    expect(screen.getByText(/ช่วงที่โมเดลมองเห็นข้างหน้า/)).toBeInTheDocument()
  })

  it('does not claim the intra-day window covers the rest of the day', () => {
    // The intra-day model only reaches +6h; a viewer at 09:00 must not read
    // the figure as "everything left today".
    render(<ForecastKpiBlock points={tomorrow} horizon="hour" isLoading={false} hasError={false} nowIso={NOW} />)
    expect(screen.getByText(/ไม่ใช่ "ทั้งวันที่เหลือ" เสมอไป/)).toBeInTheDocument()
  })

  it('says the window is empty rather than printing a confident zero', () => {
    render(<ForecastKpiBlock points={[]} horizon="day" isLoading={false} hasError={false} nowIso={NOW} />)
    expect(screen.getByText(/ยังไม่มีจุดพยากรณ์ในช่วงเวลานี้/)).toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('renders loading and error states', () => {
    const { rerender } = render(
      <ForecastKpiBlock points={[]} horizon="day" isLoading={true} hasError={false} nowIso={NOW} />,
    )
    expect(screen.getByText(/กำลังโหลดคำพยากรณ์/)).toBeInTheDocument()

    rerender(<ForecastKpiBlock points={[]} horizon="day" isLoading={false} hasError={true} nowIso={NOW} />)
    expect(screen.getByText(/ยังดึงคำพยากรณ์มาแสดงไม่ได้/)).toBeInTheDocument()
  })
})
