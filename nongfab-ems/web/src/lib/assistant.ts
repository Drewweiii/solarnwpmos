// Rule-based (no LLM, no API cost) AI-assistant logic: match the visitor's
// message against a fixed set of intents by keyword, then either return a
// canned answer or fetch real live data (via the same api.ts functions the
// dashboard's own pages already use) and fill it into the response. Kept
// framework-free (no React) so it's directly unit-testable and so a future
// "fall back to a real LLM call" step can slot in as one more intent
// (matched last, after every rule-based one has had a chance) without
// touching this file's existing structure.

import { getAssets, getForecast, getPerformance, getWeatherStrip } from './api'
import { REAL_ZONE_IDS } from './queries'
import type { PerformanceResponse } from './types'

export interface AssistantContext {
  token: string
}

export interface AssistantIntent {
  id: string
  /** Any one of these substrings appearing in the (lowercased) question is a match. */
  keywords: string[]
  respond: (question: string, ctx: AssistantContext) => Promise<string> | string
}

const ZONE_KEYWORDS: Record<string, string> = {
  gis: 'GIS',
  จีไอเอส: 'GIS',
  isb: 'ISB',
  ไอเอสบี: 'ISB',
  jetty: 'Jetty',
  เจ็ตตี้: 'Jetty',
  เจตตี้: 'Jetty',
  ท่าเรือ: 'Jetty',
}

function extractZone(question: string): string | null {
  const lower = question.toLowerCase()
  for (const [kw, zone] of Object.entries(ZONE_KEYWORDS)) {
    if (lower.includes(kw)) return zone
  }
  return null // null means "no specific zone mentioned" -> caller sums across all
}

async function fetchZonePerformance(zone: string | null, token: string): Promise<{ label: string; totals: PerformanceResponse[] }> {
  if (zone) {
    const perf = await getPerformance(zone, token)
    return { label: zone, totals: [perf] }
  }
  const all = await Promise.all(REAL_ZONE_IDS.map((z) => getPerformance(z, token)))
  return { label: 'ทุกโซน (All)', totals: all }
}

function sumField(perfs: PerformanceResponse[], field: 'ac_energy_kwh_today'): number {
  return perfs.reduce((sum, p) => sum + p[field], 0)
}

function currentPowerKw(perf: PerformanceResponse): number {
  const nowMs = Date.now()
  const nearest = perf.hourly.reduce((closest, p) =>
    Math.abs(new Date(p.timestamp).getTime() - nowMs) < Math.abs(new Date(closest.timestamp).getTime() - nowMs) ? p : closest,
  )
  return nearest.ac_kw
}

export const ASSISTANT_INTENTS: AssistantIntent[] = [
  {
    id: 'greeting',
    keywords: ['สวัสดี', 'หวัดดี', 'hello', 'hi ', 'สอบถาม'],
    respond: () =>
      'สวัสดีค่ะ ☀️ หนูช่วยตอบคำถามเกี่ยวกับเว็บนี้ได้ เช่น "ตอนนี้ผลิตไฟเท่าไหร่" "พยากรณ์พรุ่งนี้เป็นยังไง" ' +
      '"หน้า Forecast ใช้ยังไง" หรือถามความรู้ทั่วไปเรื่องโซลาร์เซลล์ก็ได้ค่ะ ลองถามมาได้เลย!',
  },
  {
    id: 'help_navigation',
    keywords: ['ใช้งานยังไง', 'ใช้ยังไง', 'หน้าไหน', 'เมนู', 'how to use', 'navigate', 'มีหน้าอะไรบ้าง'],
    respond: () =>
      'เว็บนี้มี 6 หน้าหลักค่ะ:\n' +
      '• Forecast — กราฟพยากรณ์การผลิตไฟ เทียบกับของจริง ดูได้ทั้งรายวัน/รายชั่วโมง\n' +
      '• Simulation — ทดลองสถานการณ์สมมติ เช่น เมฆเยอะขึ้น หรือแผงเสื่อมสภาพ\n' +
      '• Financial — วิเคราะห์ความคุ้มค่าการลงทุน (NPV/IRR/คืนทุน)\n' +
      '• 3D View — ดูโรงงานจำลอง 3 มิติ พร้อมเงาและเส้นทางดวงอาทิตย์\n' +
      '• Energy Report — รายงานสรุปพลังงานรายปี/รายเดือน\n' +
      '• Irradiance Map — แผนที่ความเข้มแสงอาทิตย์ในพื้นที่',
  },
  // Knowledge (canned, definitional) intents are matched before the
  // data-fetching ones below: a keyword like "kwp" appears in both a plain
  // "what is kWp" question and the live-capacity-lookup intent's own
  // keywords, and "X คือ/หมายถึง" phrasing should win that ambiguity - a
  // visitor asking what a term means wants the definition, not a live
  // data dump.
  {
    id: 'knowledge_irradiance',
    keywords: ['ความเข้มแสง', 'irradiance', 'ghi', 'w/m2', 'w/m²'],
    respond: () =>
      '"ความเข้มแสงอาทิตย์" (irradiance) คือปริมาณพลังงานแสงอาทิตย์ที่ตกกระทบพื้นที่หนึ่งตารางเมตร วัดเป็นวัตต์ต่อตารางเมตร (W/m²) ' +
      'ยิ่งค่าสูง (เช่นเที่ยงวันฟ้าใส ~800-1000 W/m²) แผงโซลาร์ก็ยิ่งผลิตไฟได้มากขึ้นค่ะ',
  },
  {
    id: 'knowledge_kwp',
    keywords: ['kwp คือ', 'kwp หมายถึง', 'what is kwp'],
    respond: () =>
      'kWp (กิโลวัตต์พีค) คือกำลังการผลิตสูงสุดของแผงโซลาร์ วัดภายใต้สภาวะทดสอบมาตรฐาน (STC: แสง 1000 W/m², อุณหภูมิ 25°C) ' +
      'ส่วน kW AC คือกำลังไฟฟ้ากระแสสลับสูงสุดที่อินเวอร์เตอร์แปลงออกมาได้จริง ซึ่งมักจะน้อยกว่า kWp เล็กน้อยค่ะ',
  },
  {
    id: 'knowledge_plant_factor',
    keywords: ['plant factor คือ', 'solar plant factor', 'capacity factor'],
    respond: () =>
      '"Solar plant factor" (หรือ capacity factor) บอกว่าโรงไฟฟ้าผลิตไฟได้กี่เปอร์เซ็นต์ของกำลังการผลิตติดตั้งเทียบกับถ้าผลิตเต็มกำลังตลอด 24 ชม. ' +
      'โซลาร์ผลิตได้แค่ตอนกลางวัน ค่านี้จึงมักอยู่ราว 0.1-0.25 เป็นเรื่องปกติ ไม่ใช่ตัวเลขที่ต่ำผิดปกติค่ะ',
  },
  {
    id: 'knowledge_forecast_horizon',
    keywords: ['day-ahead', 'intra-day', 'ต่างกันยังไง', 'minute-ahead'],
    respond: () =>
      'พยากรณ์ในเว็บนี้มี 3 ระยะ: Day-ahead (พยากรณ์ล่วงหน้าหลายวัน เหมาะกับวางแผนระยะกลาง), ' +
      'Intra-day (ล่วงหน้า 1-6 ชม. แม่นกว่าเพราะใกล้เวลาจริง), และ Minute-ahead (ล่วงหน้า 10-60 นาที ' +
      'สำหรับการเปลี่ยนแปลงเร็วๆ เช่นเมฆบัง) ค่ะ',
  },
  {
    id: 'current_power',
    // Thai has no word-order guarantee for "now"/"produce power" - cover
    // both orderings ("ผลิตไฟตอนนี้" and "ตอนนี้ผลิต...") rather than one
    // fixed phrase (found live: the assistant's own quick-reply chip
    // "ตอนนี้ผลิตไฟเท่าไหร่" didn't match the original keyword list).
    keywords: ['กำลังไฟ', 'ผลิตไฟตอนนี้', 'ตอนนี้ผลิตไฟ', 'ผลิตไฟเท่าไหร่', 'กำลังการผลิตตอนนี้', 'current power', 'power now', 'kw ตอนนี้'],
    respond: async (question, ctx) => {
      const { label, totals } = await fetchZonePerformance(extractZone(question), ctx.token)
      const totalKw = totals.reduce((sum, p) => sum + currentPowerKw(p), 0)
      return `${label} กำลังผลิตไฟอยู่ประมาณ ${totalKw.toFixed(1)} kW ในขณะนี้ค่ะ (คำนวณจากแบบจำลอง ไม่ใช่ค่าที่วัดจากมิเตอร์จริง)`
    },
  },
  {
    id: 'today_energy',
    keywords: ['วันนี้ผลิตไฟ', 'สะสมวันนี้', 'พลังงานวันนี้', 'today energy', 'kwh วันนี้', 'ผลิตไฟได้เท่าไหร่'],
    respond: async (question, ctx) => {
      const { label, totals } = await fetchZonePerformance(extractZone(question), ctx.token)
      const totalKwh = sumField(totals, 'ac_energy_kwh_today')
      return `${label} ผลิตไฟสะสมตั้งแต่เที่ยงคืนถึงตอนนี้ประมาณ ${totalKwh.toFixed(1)} kWh ค่ะ (คำนวณจากแบบจำลอง ยังไม่ใช่มิเตอร์จริง - ดูรายละเอียดที่หน้า Forecast ได้ค่ะ)`
    },
  },
  {
    id: 'forecast',
    keywords: ['พยากรณ์', 'forecast', 'พรุ่งนี้', 'ทำนาย'],
    respond: async (question, ctx) => {
      const zone = extractZone(question) ?? 'GIS'
      const result = await getForecast(zone, 'day', ctx.token)
      const first = result.points[0]
      if (!first) return `ยังไม่มีข้อมูลพยากรณ์สำหรับ ${zone} ในตอนนี้ค่ะ`
      const sourceNote = result.data_source === 'real' ? 'อิงจากข้อมูลอากาศจริง' : 'ยังใช้ข้อมูลจำลอง (ข้อมูลจริงสะสมไม่พอ)'
      return (
        `พยากรณ์การผลิตไฟของ ${zone} ในช่วงถัดไป อยู่ที่ประมาณ ${first.pred.toFixed(1)} kW ` +
        (first.lower != null && first.upper != null ? `(ช่วง ${first.lower.toFixed(1)}-${first.upper.toFixed(1)} kW) ` : '') +
        `${sourceNote}ค่ะ - ดูกราฟเต็มได้ที่หน้า Forecast`
      )
    },
  },
  {
    id: 'capacity',
    keywords: ['กำลังการผลิตติดตั้ง', 'capacity', 'ติดตั้งกี่', 'kwp', 'ขนาดโรงไฟฟ้า'],
    respond: async (_question, ctx) => {
      const registry = await getAssets(ctx.token)
      const lines = registry.zones.map((z) => `• ${z.id}: ${z.ac_capacity_kw} kW AC / ${z.dc_capacity_kwp} kWp DC${z.simulated ? ' (แผนอนาคต ยังไม่ติดตั้งจริง)' : ''}`)
      const total = registry.zones.reduce((sum, z) => sum + z.ac_capacity_kw, 0)
      return `กำลังการผลิตติดตั้งของโรงไฟฟ้า:\n${lines.join('\n')}\nรวมทั้งหมด ${total} kW AC ค่ะ`
    },
  },
  {
    id: 'weather_now',
    keywords: ['อากาศตอนนี้', 'อุณหภูมิ', 'weather', 'อากาศเป็นไง', 'ร้อนไหม'],
    respond: async (_question, ctx) => {
      const strip = await getWeatherStrip(ctx.token, 1)
      const now = Date.now()
      const nearest = strip.points.reduce((closest, p) =>
        Math.abs(new Date(p.timestamp).getTime() - now) < Math.abs(new Date(closest.timestamp).getTime() - now) ? p : closest,
      )
      const sourceNote = strip.data_source === 'real' ? 'ข้อมูลจริง' : 'ข้อมูลจำลอง'
      return `ตอนนี้อุณหภูมิที่โรงไฟฟ้าประมาณ ${nearest.temp_c.toFixed(1)}°C (${sourceNote}) ค่ะ ดูแถบอุณหภูมิเต็มได้ที่หน้า Forecast`
    },
  },
  {
    id: 'financial_info',
    keywords: ['การเงิน', 'ลงทุน', 'คืนทุน', 'roi', 'npv', 'irr', 'financial', 'คุ้มไหม'],
    respond: () =>
      'หน้า Financial คำนวณความคุ้มค่าการลงทุน (NPV/IRR/LCOE/ระยะเวลาคืนทุน) ให้ค่ะ ' +
      'แต่ตอนนี้ตัวเลขต้นทุน/ค่าไฟ/อัตราดอกเบี้ยยังเป็นค่าประมาณเบื้องต้น ยังไม่ใช่ตัวเลขจริงของโครงการนี้ ' +
      'ลองเข้าไปปรับตัวเลขเองที่หน้า Financial ได้เลยค่ะ',
  },
]

export const ASSISTANT_FALLBACK_MESSAGE =
  'ขอโทษด้วยค่ะ หนูยังไม่เข้าใจคำถามนี้ 🙏 ตอนนี้หนูตอบได้เฉพาะคำถามเกี่ยวกับ: การใช้งานเว็บ, ข้อมูลกำลังไฟ/พลังงานจริงในระบบ, ' +
  'พยากรณ์, และความรู้ทั่วไปเรื่องโซลาร์เซลล์ ลองถามใหม่อีกครั้งได้ไหมคะ?'

/** Finds the first matching intent (by keyword substring) and runs it,
 * falling back to ASSISTANT_FALLBACK_MESSAGE if nothing matches or the
 * matched intent's own data fetch fails. */
export async function answerQuestion(question: string, ctx: AssistantContext): Promise<string> {
  const lower = question.toLowerCase()
  const intent = ASSISTANT_INTENTS.find((i) => i.keywords.some((kw) => lower.includes(kw)))
  if (!intent) return ASSISTANT_FALLBACK_MESSAGE

  try {
    return await intent.respond(question, ctx)
  } catch {
    return 'ขอโทษด้วยค่ะ ดึงข้อมูลไม่สำเร็จตอนนี้ ลองใหม่อีกครั้งได้ไหมคะ?'
  }
}
