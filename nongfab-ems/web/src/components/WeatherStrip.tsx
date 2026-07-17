import { useEffect, useState } from 'react'
import { WEATHER_ICON_GLYPH, weatherIconFor } from '../lib/chartData'
import { formatHourIct } from '../lib/timeScrub'
import type { ForecastDataSource, WeatherStripPoint } from '../lib/types'
import { buildStripBlocks, fractionIntoHour } from '../lib/weatherStrip'
import './WeatherStrip.css'

interface WeatherStripProps {
  points: WeatherStripPoint[]
  dataSource: ForecastDataSource | undefined
  isLoading: boolean
  hoursEachSide?: number
}

// Updated once a second: cheap (just Date math + a re-render of ~10 small
// blocks), and combined with the track's own `transition: transform 1s
// linear` (WeatherStrip.css) it reads as continuous smooth motion rather
// than a once-a-second jump - "เลื่อนช้าๆ เดี๋ยวเวียนหัว" (slide slowly,
// don't want it dizzying) was the explicit ask, and a full block-width slide
// takes a whole hour at this rate, so per-tick motion is imperceptible.
const TICK_MS = 1000

/** A horizontally-scrolling "conveyor belt" of hourly weather blocks,
 * continuously centered on the real current hour (not a handful of fixed
 * checkpoints) - see weatherStrip.ts for the pure position/matching math
 * this component only renders. A fixed vertical marker sits at the
 * viewport's dead center representing "now"; blocks slide left underneath
 * it in real time, landing exactly centered on the marker only at the top
 * of each hour (mid-hour, the marker sits in the gap between the two
 * neighboring hour blocks) - matching the behavior spelled out in the
 * original request (14:00 centered -> 14:30 gap between 14:00/15:00 ->
 * 15:00 centered).
 */
export function WeatherStrip({ points, dataSource, isLoading, hoursEachSide = 4 }: WeatherStripProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), TICK_MS)
    return () => window.clearInterval(id)
  }, [])

  const blocks = buildStripBlocks(points, now, hoursEachSide)
  const fraction = fractionIntoHour(now)

  const totalBlocks = blocks.length // 2*hoursEachSide + 2 (one extra sliding in from the right)
  const visibleBlocks = totalBlocks - 1 // 2*hoursEachSide + 1, what the viewport actually shows at fraction=0

  // Percentages here are relative to the *track* (the flex row), not the
  // viewport - `transform: translateX(x%)` is defined relative to the
  // transformed element's own box per the CSS spec, so blockWidthPct% of
  // the track equals exactly one block's real pixel width regardless of
  // the viewport's actual rendered size (no ResizeObserver/JS measurement
  // needed).
  const trackWidthPct = (totalBlocks / visibleBlocks) * 100
  const blockWidthPct = 100 / totalBlocks
  const translateXPct = -fraction * blockWidthPct

  return (
    <section className="weather-strip" aria-label="Weather forecast">
      <div className="weather-strip-header">
        <span className="weather-strip-title">อุณหภูมิรายชั่วโมง / Hourly temperature</span>
        {!isLoading && dataSource && (
          <span
            className={
              dataSource === 'real' ? 'data-source-badge data-source-badge-real' : 'data-source-badge data-source-badge-synthetic'
            }
          >
            {dataSource === 'real' ? 'Real data' : 'Demo data'}
          </span>
        )}
      </div>
      {isLoading ? (
        <p className="forecast-status">Loading…</p>
      ) : (
        <div className="weather-strip-viewport">
          <div className="weather-strip-now-marker" aria-hidden="true" />
          <div className="weather-strip-track" style={{ width: `${trackWidthPct}%`, transform: `translateX(${translateXPct}%)` }}>
            {blocks.map((block) => (
              <div key={block.key} className="weather-strip-item" style={{ width: `${blockWidthPct}%` }}>
                <span className="weather-strip-hour">{formatHourIct(block.timestamp)}</span>
                {block.ssrd_w_m2 != null ? (
                  <span className="weather-strip-icon" aria-hidden="true">
                    {WEATHER_ICON_GLYPH[weatherIconFor(block.ssrd_w_m2)]}
                  </span>
                ) : (
                  <span className="weather-strip-icon weather-strip-icon-empty" aria-hidden="true">
                    ·
                  </span>
                )}
                <span className="weather-strip-temp">{block.temp_c != null ? `${block.temp_c.toFixed(1)}°C` : '—'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
