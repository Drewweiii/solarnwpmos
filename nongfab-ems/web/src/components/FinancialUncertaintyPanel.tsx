import type { FinancialUncertainty, MetricPercentiles } from '../lib/types'

/** The spread behind the single NPV (2026-07-25, project B).
 *
 * Two things are shown separately because they mean different things: the
 * P50/P90 table is how much the SUN varies year to year, while the Monte Carlo
 * band is how unsure the MONEY assumptions are. On this project the second is
 * far wider than the first, and saying so is the point - a confident-looking
 * payback figure resting on a placeholder CAPEX is the thing this panel exists
 * to stop.
 *
 * Direction matters per metric and is the easiest thing here to misread: a high
 * NPV is good, a high payback is bad. So each row states which end is the
 * pessimistic case rather than leaving the reader to infer it from "P10".
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })
const nf2 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 2 })

interface Row {
  metric: string
  label: string
  unit: string
  /** true when a SMALLER number is the better outcome (payback, LCOE). */
  lowerIsBetter: boolean
  format: (v: number) => string
}

const ROWS: Row[] = [
  { metric: 'npv_thb', label: 'NPV (มูลค่าปัจจุบันสุทธิ)', unit: 'บาท', lowerIsBetter: false, format: (v) => nf0.format(v) },
  { metric: 'irr_pct', label: 'IRR (ผลตอบแทนภายใน)', unit: '%', lowerIsBetter: false, format: (v) => nf2.format(v) },
  { metric: 'simple_payback_years', label: 'ระยะคืนทุน', unit: 'ปี', lowerIsBetter: true, format: (v) => nf2.format(v) },
  { metric: 'lcoe_thb_per_kwh', label: 'LCOE (ต้นทุนต่อหน่วย)', unit: 'บาท/kWh', lowerIsBetter: true, format: (v) => nf2.format(v) },
]

/** The pessimistic and optimistic ends for a metric, given its direction.
 * Exported for tests: getting this backwards would present the best case as
 * the worst, which is the exact failure this panel is meant to prevent. */
export function orientBand(m: MetricPercentiles, lowerIsBetter: boolean): { bad: number | null; mid: number | null; good: number | null } {
  return lowerIsBetter ? { bad: m.p90, mid: m.p50, good: m.p10 } : { bad: m.p10, mid: m.p50, good: m.p90 }
}

export function FinancialUncertaintyPanel({ uncertainty }: { uncertainty: FinancialUncertainty | null | undefined }) {
  if (!uncertainty) return null

  if (!uncertainty.available) {
    return (
      <section className="financial-uncertainty" aria-label="ช่วงความไม่แน่นอน">
        <h3>ช่วงความไม่แน่นอน (P50/P90 และ Monte Carlo)</h3>
        <p className="forecast-status forecast-status-warn">{uncertainty.reason ?? 'ยังไม่มีช่วงให้แสดง'}</p>
      </section>
    )
  }

  const byMetric = new Map(uncertainty.metrics.map((m) => [m.metric, m]))
  const p50 = uncertainty.yield_levels.find((l) => l.label === 'P50')
  const p90 = uncertainty.yield_levels.find((l) => l.label === 'P90')
  const shortfall = p50 && p90 ? p50.annual_energy_kwh - p90.annual_energy_kwh : null

  return (
    <section className="financial-uncertainty" aria-label="ช่วงความไม่แน่นอน">
      <h3>ช่วงความไม่แน่นอน (P50/P90 และ Monte Carlo)</h3>

      {/* 1. Sun variability - the narrow, well-understood part. */}
      <h4 className="financial-uncertainty-sub">พลังงานรายปี — ปีที่แดดดีกับปีที่แดดไม่ดี</h4>
      <div className="financial-uncertainty-yields">
        {uncertainty.yield_levels.map((level) => (
          <div key={level.label} className="financial-uncertainty-yield">
            <span className="financial-uncertainty-yield-label">{level.label}</span>
            <strong>{nf0.format(level.annual_energy_kwh)} kWh</strong>
            <span className="financial-uncertainty-yield-sub">
              {level.label === 'P50' ? 'ค่ากลาง — ครึ่งหนึ่งของปีจะได้มากกว่านี้' : 'ระดับที่ 90% ของปีจะทำได้เกิน (กรณีอนุรักษ์นิยม)'}
            </span>
          </div>
        ))}
      </div>
      {shortfall != null && shortfall > 0 && (
        <p className="financial-uncertainty-note">
          ปีที่แย่แบบ P90 ผลิตได้น้อยกว่าค่ากลางราว <strong>{nf0.format(shortfall)} kWh/ปี</strong> — ธนาคารมักใช้ระดับ P90 ในการพิจารณาสินเชื่อ
        </p>
      )}

      {/* 2. Assumption uncertainty - the wide part, and the honest headline. */}
      <h4 className="financial-uncertainty-sub">
        ผลลัพธ์ทางการเงินเมื่อสุ่มสมมติฐาน {nf0.format(uncertainty.samples)} รอบ
      </h4>
      <div className="financial-uncertainty-scroll">
        <table className="financial-uncertainty-table">
          <thead>
            <tr>
              <th>ตัวชี้วัด</th>
              <th>กรณีแย่</th>
              <th>ค่ากลาง</th>
              <th>กรณีดี</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const m = byMetric.get(row.metric)
              if (!m) return null
              const { bad, mid, good } = orientBand(m, row.lowerIsBetter)
              const show = (v: number | null) => (v == null ? '—' : row.format(v))
              return (
                <tr key={row.metric}>
                  <td>
                    {row.label}
                    <span className="financial-uncertainty-unit"> ({row.unit})</span>
                    {m.undefined_trials > 0 && (
                      <span className="financial-uncertainty-undef">
                        {' '}
                        · {nf0.format(m.undefined_trials)} รอบไม่นิยาม
                      </span>
                    )}
                  </td>
                  <td className="financial-uncertainty-bad">{show(bad)}</td>
                  <td className="financial-uncertainty-mid">{show(mid)}</td>
                  <td className="financial-uncertainty-good">{show(good)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="financial-uncertainty-risk">
        โอกาสที่โครงการจะ <strong>ขาดทุน</strong> (NPV ติดลบ) ภายใต้สมมติฐานชุดนี้:{' '}
        <strong>{nf2.format(uncertainty.probability_npv_negative_pct)}%</strong> · โอกาสที่จะ{' '}
        <strong>ไม่คืนทุน</strong> ภายในอายุโครงการ: <strong>{nf2.format(uncertainty.probability_no_payback_pct)}%</strong>
      </p>

      <p className="financial-uncertainty-note">{uncertainty.method_note}</p>
    </section>
  )
}
