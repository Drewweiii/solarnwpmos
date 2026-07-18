import { beforeEach, describe, expect, it, vi } from 'vitest'
import { answerQuestion, ASSISTANT_FALLBACK_MESSAGE } from '../assistant'
import * as api from '../api'
import type { AssetRegistry, ForecastResponse, PerformanceResponse, WeatherStripResponse } from '../types'

function makePerformance(zone: string, ac_kw: number, ac_energy_kwh_today: number): PerformanceResponse {
  return {
    zone,
    simulated_zone: false,
    latitude: 12.68,
    longitude: 101.12,
    ac_energy_kwh_today,
    poa_irradiance_kwh_per_m2_today: 5,
    performance_ratio: 0.8,
    specific_yield_kwh_per_kwp_today: 4,
    loss_breakdown: {},
    hourly: [{ timestamp: new Date().toISOString(), ac_kw, ssrd_w_m2: 500, temp_c: 30 }],
    cloud_factor: 0.5,
  }
}

const ctx = { token: 'fake-token' }

describe('answerQuestion', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns the fallback message when nothing matches', async () => {
    const answer = await answerQuestion('อยากรู้เรื่องดวงจันทร์', ctx)
    expect(answer).toBe(ASSISTANT_FALLBACK_MESSAGE)
  })

  it('answers a greeting without touching the network', async () => {
    const spy = vi.spyOn(api, 'getPerformance')
    const answer = await answerQuestion('สวัสดีครับ', ctx)
    expect(answer).toMatch(/สวัสดี/)
    expect(spy).not.toHaveBeenCalled()
  })

  it('answers current-power questions using real fetched performance data, summed across all zones by default', async () => {
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) =>
      Promise.resolve(makePerformance(zone, { GIS: 10, ISB: 20, Jetty: 30 }[zone] ?? 0, 0)),
    )
    const answer = await answerQuestion('ตอนนี้กำลังไฟเท่าไหร่', ctx)
    expect(answer).toContain('60.0 kW') // 10+20+30
    expect(answer).toContain('ทุกโซน')
  })

  it('answers current-power questions for a specific zone mentioned by name', async () => {
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) => Promise.resolve(makePerformance(zone, 42.0, 0)))
    const answer = await answerQuestion('gis ผลิตไฟตอนนี้เท่าไหร่', ctx)
    expect(answer).toContain('42.0 kW')
    expect(api.getPerformance).toHaveBeenCalledWith('GIS', ctx.token)
  })

  it('answers today-energy questions by summing ac_energy_kwh_today', async () => {
    vi.spyOn(api, 'getPerformance').mockImplementation((zone) =>
      Promise.resolve(makePerformance(zone, 0, { GIS: 5, ISB: 10, Jetty: 15 }[zone] ?? 0)),
    )
    const answer = await answerQuestion('วันนี้ผลิตไฟได้เท่าไหร่', ctx)
    expect(answer).toContain('30.0 kWh')
  })

  it('answers forecast questions using getForecast, honestly labeling real vs synthetic', async () => {
    const forecast: ForecastResponse = {
      zone: 'GIS',
      horizon: 'day',
      issued_at: new Date().toISOString(),
      model_version: 1,
      points: [{ timestamp: new Date().toISOString(), pred: 25.5, lower: 20, upper: 30, algorithm: 'neuralprophet', error: null }],
      data_source: 'real',
      model_type: 'ml',
    }
    vi.spyOn(api, 'getForecast').mockResolvedValue(forecast)
    const answer = await answerQuestion('พยากรณ์พรุ่งนี้เป็นยังไง', ctx)
    expect(answer).toContain('25.5 kW')
    expect(answer).toContain('ข้อมูลอากาศจริง')
  })

  it('answers capacity questions by listing every zone from getAssets', async () => {
    const registry: AssetRegistry = {
      zones: [
        {
          id: 'GIS', name_full: 'GIS', ac_capacity_kw: 50, dc_capacity_kwp: 60, dc_ac_ratio: 1.2, module_count: 1,
          module_power_w: 715, inverter_model: 'x', inverter_count: 1, centroid: { lat: 0, lon: 0, elevation_m: null, note: null },
          simulated: false, module_detail: null, inverter_detail: null,
        },
      ],
    }
    vi.spyOn(api, 'getAssets').mockResolvedValue(registry)
    const answer = await answerQuestion('capacity มีกี่ kwp', ctx)
    expect(answer).toContain('GIS: 50 kW AC / 60 kWp DC')
  })

  it('answers weather questions using getWeatherStrip', async () => {
    const strip: WeatherStripResponse = {
      data_source: 'synthetic',
      points: [{ timestamp: new Date().toISOString(), temp_c: 31.2, ssrd_w_m2: 600 }],
    }
    vi.spyOn(api, 'getWeatherStrip').mockResolvedValue(strip)
    const answer = await answerQuestion('อุณหภูมิตอนนี้เท่าไหร่', ctx)
    expect(answer).toContain('31.2')
  })

  it('answers general-knowledge questions with a canned explanation, no network call', async () => {
    const spy = vi.spyOn(api, 'getPerformance')
    const answer = await answerQuestion('kWp คือ อะไร', ctx)
    expect(answer).toMatch(/กิโลวัตต์พีค/)
    expect(spy).not.toHaveBeenCalled()
  })

  it('falls back to a friendly error message if the matched intent fetch throws', async () => {
    vi.spyOn(api, 'getPerformance').mockRejectedValue(new Error('network down'))
    const answer = await answerQuestion('ตอนนี้กำลังไฟเท่าไหร่', ctx)
    expect(answer).toMatch(/ดึงข้อมูลไม่สำเร็จ/)
  })
})
