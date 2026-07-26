import { useMemo, useRef } from 'react'
import { usePoster } from '../lib/queries'
import { buildPosterGeometry, posterFilename, spokeColour, svgToBlob, HOUR_MAX, HOUR_MIN } from '../lib/yearPoster'
import './YearPoster.css'

/** "หนึ่งปีของแสงที่หนองแฟบ" — one image made of this site's own year
 * (project S, 2026-07-26).
 *
 * A radial dial: 365 rays, one per day, each a segment running from that day's
 * sunrise to its sunset. The ring the segments trace is the site's daylight
 * window breathing through the seasons - widest around day 171, narrowest
 * around day 354, both read off the data rather than assumed to be the
 * solstices.
 *
 * SHAPE AND COLOUR ARE AT DIFFERENT RESOLUTIONS ON PURPOSE, AND THE IMAGE SAYS
 * SO. The shape is per-day and exact: pvlib solar geometry at Nong Fab's real
 * coordinates, astronomy rather than measurement. The colour is per-month and
 * modelled, because the annual energy estimate genuinely *is* twelve
 * representative days. A per-day colour gradient would have looked better and
 * would have invented 353 numbers - the same fabrication as an unlabelled
 * figure, in pixels.
 *
 * Downloads as SVG by serialising the live node, so the file cannot differ
 * from what the viewer saw.
 */

const nf0 = new Intl.NumberFormat('th-TH', { maximumFractionDigits: 0 })

function dayOfYearLabel(dayOfYear: number, year: number): string {
  const d = new Date(Date.UTC(year, 0, dayOfYear))
  return new Intl.DateTimeFormat('th-TH', { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(d)
}

export function YearPoster({ zone }: { zone: string }) {
  const { data, isLoading, isError } = usePoster(zone)
  const svgRef = useRef<SVGSVGElement>(null)

  const geometry = useMemo(() => (data ? buildPosterGeometry(data) : null), [data])

  const download = () => {
    const svg = svgRef.current
    if (!svg || !data) return
    const url = URL.createObjectURL(svgToBlob(svg))
    const a = document.createElement('a')
    a.href = url
    a.download = posterFilename(data.zone, data.year)
    a.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading) {
    return (
      <section className="year-poster">
        <h2>หนึ่งปีของแสงที่หนองแฟบ</h2>
        <p className="grid-context-stat-sub">กำลังคำนวณเวลาขึ้น-ตกของดวงอาทิตย์ทั้งปี …</p>
      </section>
    )
  }

  if (isError || !data || !geometry) {
    return (
      <section className="year-poster">
        <h2>หนึ่งปีของแสงที่หนองแฟบ</h2>
        <p className="grid-context-stat-sub">ยังสร้างภาพนี้ไม่ได้ในขณะนี้</p>
      </section>
    )
  }

  const { size, centre, spokes, monthTicks, hourRings } = geometry

  return (
    <section className="year-poster" aria-label="โปสเตอร์หนึ่งปีของแสง">
      <div className="year-poster-head">
        <h2>หนึ่งปีของแสงที่หนองแฟบ</h2>
        <button type="button" className="year-poster-download print-hide" onClick={download}>
          ⬇ ดาวน์โหลด SVG
        </button>
      </div>

      <div className="year-poster-frame">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${size} ${size}`}
          className="year-poster-svg"
          role="img"
          aria-label={`วงกลมแสดงเวลาขึ้น-ตกของดวงอาทิตย์ทุกวันตลอดปี ${data.year} ที่โซน ${data.zone}`}
        >
          <rect width={size} height={size} className="year-poster-bg" />

          {/* Hour rings first, so every ray sits on top of them. */}
          {hourRings.map((ring) => (
            <g key={ring.hour}>
              <circle cx={centre} cy={centre} r={ring.radius} className="year-poster-ring" />
              <text x={centre} y={centre - ring.radius - 3} className="year-poster-ring-label">
                {String(ring.hour).padStart(2, '0')}:00
              </text>
            </g>
          ))}

          {spokes.map((s, i) => (
            <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={spokeColour(s)} strokeWidth={size / 420} />
          ))}

          {monthTicks.map((t) => (
            <g key={t.label}>
              <line x1={t.lineX1} y1={t.lineY1} x2={t.lineX2} y2={t.lineY2} className="year-poster-month-rule" />
              <text x={t.x} y={t.y} className="year-poster-month-label">
                {t.label}
              </text>
            </g>
          ))}

          <text x={centre} y={centre - size * 0.045} className="year-poster-centre-title">
            {nf0.format(data.annual_ac_energy_kwh)}
          </text>
          <text x={centre} y={centre - size * 0.012} className="year-poster-centre-sub">
            kWh/ปี · โซน {data.zone} · {data.year}
          </text>
          <text x={centre} y={centre + size * 0.028} className="year-poster-centre-sub">
            {data.lat.toFixed(2)}°N {data.lon.toFixed(2)}°E
          </text>
          <text x={centre} y={centre + size * 0.058} className="year-poster-centre-sub">
            วงใน = พระอาทิตย์ขึ้น · วงนอก = พระอาทิตย์ตก ({HOUR_MIN}:00–{HOUR_MAX}:00 น.)
          </text>
        </svg>
      </div>

      <div className="year-poster-legend">
        <span>
          <i className="year-poster-swatch year-poster-swatch-dry" /> ฤดูแล้ง
        </span>
        <span>
          <i className="year-poster-swatch year-poster-swatch-rain" /> ฤดูฝน (มิ.ย.–ต.ค.)
        </span>
        <span>ยิ่งสีเข้ม = เดือนนั้นผลิตได้มาก</span>
      </div>

      <p className="grid-context-stat-sub">
        กลางวันยาวที่สุด <strong>{dayOfYearLabel(data.longest_day, data.year)}</strong> · สั้นที่สุด{' '}
        <strong>{dayOfYearLabel(data.shortest_day, data.year)}</strong> — อ่านจากตัวเลขที่วาด ไม่ได้สมมติว่าเป็นวันครีษมายัน/เหมายัน
      </p>
      <p className="grid-context-stat-sub">{data.geometry_note}</p>
      <p className="grid-context-stat-sub">{data.energy_note}</p>
      <p className="grid-context-stat-sub orientation-assumed">{data.why_note}</p>
    </section>
  )
}
