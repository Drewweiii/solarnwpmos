import { useMemo } from 'react'
import { computeForecastKpi, pointsAhead, pointsForTomorrow } from '../lib/forecastKpi'
import { formatHourIct } from '../lib/timeScrub'
import type { ForecastPoint } from '../lib/types'
import { Provenanced } from './Provenanced'

/** The big-number block for the forecast itself (2026-07-25).
 *
 * The page's existing `kpi-row` describes the plant as it is right now. This
 * one describes what the model says is coming, which is what the page is for -
 * four numbers a viewer can read from across the room: how much energy, how big
 * the peak and when, how wide the uncertainty is, and how long the array will
 * be running.
 *
 * It follows the Day-ahead / Intra-day toggle rather than sitting on one of
 * them, because the same four questions have different answers per horizon and
 * a viewer switching tabs is asking them again.
 *
 * Every tile renders "—" rather than a zero when it has nothing: a confident
 * "0 kWh" and "no forecast yet" look identical otherwise, and only one of them
 * is true.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 1 })

interface Props {
  points: ForecastPoint[]
  horizon: 'day' | 'hour'
  isLoading: boolean
  hasError: boolean
  /** Injectable for tests; the window boundaries are time-dependent and a test
   * that depends on the wall clock fails at 07:00 ICT and nowhere else. */
  nowIso?: string
}

interface TileProps {
  label: string
  value: string
  unit?: string
  sub?: string
  accent?: boolean
  /** A key from GET /provenance. Set it and the tile's label grows a ⓘ that
   * opens the chain behind the number (project O). Only the tiles whose figure
   * actually has a registered chain get one - a ⓘ that opens an error would be
   * worse than no ⓘ. */
  provenanceKey?: string
}

function BigTile({ label, value, unit, sub, accent, provenanceKey }: TileProps) {
  return (
    <div className={accent ? 'forecast-kpi-tile forecast-kpi-tile-accent' : 'forecast-kpi-tile'}>
      <span className="forecast-kpi-tile-label">
        {provenanceKey ? <Provenanced valueKey={provenanceKey}>{label}</Provenanced> : label}
      </span>
      <span className="forecast-kpi-tile-value">
        {value}
        {unit && <span className="forecast-kpi-tile-unit"> {unit}</span>}
      </span>
      <span className="forecast-kpi-tile-sub">{sub ?? ' '}</span>
    </div>
  )
}

export function ForecastKpiBlock({ points, horizon, isLoading, hasError, nowIso }: Props) {
  const now = nowIso ?? new Date().toISOString()

  const { kpi, windowLabel, windowNote } = useMemo(() => {
    if (horizon === 'day') {
      const tomorrow = pointsForTomorrow(points, now)
      return {
        kpi: computeForecastKpi(tomorrow),
        windowLabel: 'พรุ่งนี้ทั้งวัน',
        windowNote: 'นับตามวันที่แบบไทย (ICT) ไม่ใช่ UTC',
      }
    }
    const ahead = pointsAhead(points, now)
    return {
      kpi: computeForecastKpi(ahead),
      windowLabel: 'ช่วงที่โมเดลมองเห็นข้างหน้า',
      // Deliberately not "the rest of today": the intra-day model only reaches
      // +6h, so late in the afternoon those are the same window and at 09:00
      // they are very much not.
      windowNote: 'โมเดล Intra-day พยากรณ์ล่วงหน้าได้ 6 ชั่วโมง จึงไม่ใช่ "ทั้งวันที่เหลือ" เสมอไป',
    }
  }, [points, horizon, now])

  if (isLoading) {
    return (
      <section className="forecast-kpi-block" aria-label="Forecast headline figures">
        <p className="forecast-kpi-status">กำลังโหลดคำพยากรณ์ …</p>
      </section>
    )
  }

  if (hasError) {
    return (
      <section className="forecast-kpi-block" aria-label="Forecast headline figures">
        <p className="forecast-kpi-status">ยังดึงคำพยากรณ์มาแสดงไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  const empty = kpi.pointCount === 0

  return (
    <section className="forecast-kpi-block" aria-label="Forecast headline figures">
      <div className="forecast-kpi-header">
        <h3 className="forecast-kpi-heading">คำพยากรณ์บอกอะไร — {windowLabel}</h3>
        <span className="forecast-kpi-window-note">{windowNote}</span>
      </div>

      {empty ? (
        <p className="forecast-kpi-status">
          ยังไม่มีจุดพยากรณ์ในช่วงเวลานี้ — {horizon === 'day' ? 'โมเดลรายวันยังไม่ครอบคลุมถึงพรุ่งนี้' : 'ยังไม่มีชั่วโมงข้างหน้าให้พยากรณ์'}
        </p>
      ) : (
        <div className="forecast-kpi-tiles">
          <BigTile
            label="พลังงานที่คาดว่าจะผลิตได้"
            value={kpi.energyKwh === null ? '—' : nf0.format(kpi.energyKwh)}
            unit="kWh"
            sub={`จาก ${kpi.pointCount} จุดพยากรณ์ ทุก ${nf1.format(kpi.stepHours)} ชม.`}
            accent
            provenanceKey="forecast.expected_energy_kwh"
          />
          <BigTile
            label="กำลังผลิตสูงสุดที่คาด"
            value={kpi.peakKw === null ? '—' : nf1.format(kpi.peakKw)}
            unit="kW"
            sub={kpi.peakAtIso ? `เวลา ${formatHourIct(kpi.peakAtIso)} น.` : undefined}
          />
          <BigTile
            label="ความไม่แน่นอน ณ จุดพีค"
            value={kpi.bandPct === null ? '—' : `±${nf0.format(kpi.bandPct)}%`}
            sub={
              kpi.bandKw === null
                ? 'โมเดลสำรองเชิงฟิสิกส์ไม่ได้ให้ช่วงความเชื่อมั่น'
                : `±${nf1.format(kpi.bandKw)} kW (ช่วง P10–P90)`
            }
          />
          <BigTile
            label="ระยะเวลาที่จะผลิตไฟ"
            value={kpi.productiveHours === null ? '—' : nf1.format(kpi.productiveHours)}
            unit="ชม."
            sub="ชั่วโมงที่กำลังผลิตเกิน 5% ของพีควันนั้น"
          />
        </div>
      )}
    </section>
  )
}
