import { beforeEach, describe, expect, it, vi } from 'vitest'
import { answerQuestion, answerQuestionWithMood, ASSISTANT_FALLBACK_MESSAGE, TOP_LEVEL_OPTIONS } from '../assistant'
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
    history: [],
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
      points: [
        { timestamp: new Date().toISOString(), pred: 25.5, lower: 20, upper: 30, algorithm: 'neuralprophet', error: null, candidate_errors: null },
      ],
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

  it('speaks as a male character (ผม/ครับ), never the female หนู/ค่ะ/คะ', async () => {
    const answer = await answerQuestion('kWp คือ อะไร', ctx)
    expect(answer).not.toMatch(/หนู|ค่ะ|คะ/)
  })
})

describe('answerQuestionWithMood', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('reports mood "happy" for a real matched answer', async () => {
    const result = await answerQuestionWithMood('kWp คือ อะไร', ctx)
    expect(result.mood).toBe('happy')
    expect(result.text).toMatch(/กิโลวัตต์พีค/)
  })

  it('reports mood "sad" when nothing matches, and offers the top-level categories as a next step', async () => {
    const result = await answerQuestionWithMood('อยากรู้เรื่องดวงจันทร์', ctx)
    expect(result.mood).toBe('sad')
    expect(result.text).toBe(ASSISTANT_FALLBACK_MESSAGE)
    expect(result.options?.length).toBeGreaterThan(0)
    expect(result.options?.every((o) => o.kind === 'category')).toBe(true)
  })

  it('reports mood "sad" when the matched intent fetch throws, and still offers a next step', async () => {
    vi.spyOn(api, 'getPerformance').mockRejectedValue(new Error('network down'))
    const result = await answerQuestionWithMood('ตอนนี้กำลังไฟเท่าไหร่', ctx)
    expect(result.mood).toBe('sad')
    expect(result.text).toMatch(/ดึงข้อมูลไม่สำเร็จ/)
    expect(result.options?.length).toBeGreaterThan(0)
  })

  it('answers a guided topic sub-question and suggests its sibling questions as follow-ups', async () => {
    const result = await answerQuestionWithMood('Inverter คืออะไร', ctx)
    expect(result.mood).toBe('happy')
    expect(result.text).toMatch(/นักแปลภาษาไฟฟ้า/)
    const questionLabels = result.options?.filter((o) => o.kind === 'question').map((o) => o.label)
    expect(questionLabels).toContain('สำคัญยังไง')
    expect(questionLabels).toContain('ทำไมใช้ Huawei')
  })

  it('a bare keyword with no specific question offers a clarifying menu instead of guessing', async () => {
    const result = await answerQuestionWithMood('inverter', ctx)
    expect(result.mood).toBe('happy')
    expect(result.text).toMatch(/Inverter/)
    const questions = result.options?.filter((o) => o.kind === 'question').map((o) => o.label)
    expect(questions).toEqual(['Inverter คืออะไร', 'สำคัญยังไง', 'ทำไมใช้ Huawei'])
  })

  it('prefers the longer, more specific keyword match over a shorter unrelated one', async () => {
    // "หน้า Forecast ในเว็บนี้ใช้ดูอะไรได้บ้าง" contains the bare 'forecast'
    // keyword (a live-data-fetching intent) as a substring, but the intended
    // match is the "how to use this page" guided answer, not a live forecast.
    const result = await answerQuestionWithMood('หน้า Forecast ในเว็บนี้ใช้ดูอะไรได้บ้าง', ctx)
    expect(result.text).toMatch(/กราฟพยากรณ์การผลิตไฟฟ้า/)
  })

  it('a hand-written (non-topic) intent still offers the top-level categories as a next step', async () => {
    const result = await answerQuestionWithMood('สวัสดีครับ', ctx)
    expect(result.options?.length).toBeGreaterThan(0)
    expect(result.options?.every((o) => o.kind === 'category')).toBe(true)
  })
})

describe('Forecasting guided Q&A category', () => {
  it('explains which model handles each horizon, grounded in the real model names', async () => {
    const result = await answerQuestionWithMood('พยากรณ์แต่ละระยะเวลาใช้โมเดลอะไร ทำไมถึงเลือกโมเดลนั้น', ctx)
    expect(result.text).toMatch(/CNN-LSTM/)
    expect(result.text).toMatch(/LightGBM/)
    expect(result.text).toMatch(/Random Forest/)
    expect(result.text).toMatch(/Sum-k LSTM/)
    expect(result.text).toMatch(/NeuralProphet/)
  })

  it('is honest that RMSE is currently measured against a physics model, not real SCADA telemetry', async () => {
    const result = await answerQuestionWithMood('รู้ได้ยังไงว่าพยากรณ์การผลิตไฟแม่นแค่ไหน', ctx)
    expect(result.text).toMatch(/RMSE/)
    expect(result.text).toMatch(/ไม่ใช่ค่าที่วัดจากมิเตอร์จริง/)
  })

  it('is included as a 4th top-level browse category', () => {
    const categoryLabels = TOP_LEVEL_OPTIONS.map((o) => o.label)
    expect(categoryLabels.some((l) => l.includes('พยากรณ์'))).toBe(true)
    expect(TOP_LEVEL_OPTIONS).toHaveLength(4)
  })
})

describe('role-aware answers (Simulation/Financial are operator-and-up only)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('lists all pages including Simulation/Financial for a non-viewer role', async () => {
    const result = await answerQuestionWithMood('มีหน้าอะไรบ้าง', { token: 'x', role: 'operator' })
    expect(result.text).toContain('Simulation')
    expect(result.text).toContain('Financial')
  })

  it('omits Simulation/Financial bullets from the page list for a viewer, but explains why in a closing note', async () => {
    const result = await answerQuestionWithMood('มีหน้าอะไรบ้าง', { token: 'x', role: 'viewer' })
    expect(result.text).not.toContain('• Simulation')
    expect(result.text).not.toContain('• Financial')
    expect(result.text).toMatch(/operator/)
  })

  it('tells a viewer Financial is operator-and-up instead of walking them through using it', async () => {
    const result = await answerQuestionWithMood('การลงทุนคุ้มไหม', { token: 'x', role: 'viewer' })
    expect(result.text).toMatch(/operator/)
    expect(result.text).not.toMatch(/NPV\/IRR/)
  })

  it('still explains Financial normally for an operator/admin', async () => {
    const result = await answerQuestionWithMood('การลงทุนคุ้มไหม', { token: 'x', role: 'operator' })
    expect(result.text).toMatch(/NPV\/IRR/)
  })

  it('defaults to the non-viewer (unrestricted) behavior when role is missing entirely', async () => {
    const result = await answerQuestionWithMood('มีหน้าอะไรบ้าง', { token: 'x' })
    expect(result.text).toContain('Simulation')
    expect(result.text).toContain('Financial')
  })
})
