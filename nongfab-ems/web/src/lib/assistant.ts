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
import { findClarifyGroup, findGroupBySubQuestionId, TOPIC_CATEGORIES } from './assistantTopics'
import { TOPIC_ANSWERS } from './assistantContent'
import type { PerformanceResponse } from './types'

export interface AssistantContext {
  token: string
  /** Optional - only used to keep a couple of canned answers (page listing,
   * Financial) honest about what a viewer can actually reach. Simulation/
   * Financial are operator-and-up only (Layout.tsx/App.tsx's
   * RequireOperator, 2026-07-18) - a viewer asking about them should be told
   * that plainly, not walked through using a page they can't open. Missing/
   * unknown role is treated the same as non-viewer (never hides anything by
   * default). */
  role?: string | null
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

// The assistant is "น้อง Solar" (he/him) - a named male character, not a
// generic "AI assistant" - so every canned response speaks in first-person
// masculine Thai (ผม/ครับ, never หนู/ค่ะ/คะ).
const HAND_WRITTEN_INTENTS: AssistantIntent[] = [
  {
    id: 'greeting',
    keywords: ['สวัสดี', 'หวัดดี', 'hello', 'hi ', 'สอบถาม'],
    respond: () =>
      'สวัสดีครับ ☀️ ผมชื่อ "น้อง Solar" ผู้ช่วย AI ของเว็บนี้ครับ ผมช่วยตอบคำถามเกี่ยวกับเว็บนี้ได้ เช่น "ตอนนี้ผลิตไฟเท่าไหร่" "พยากรณ์พรุ่งนี้เป็นยังไง" ' +
      '"หน้า Forecast ใช้ยังไง" หรือถามความรู้ทั่วไปเรื่องโซลาร์เซลล์ก็ได้ครับ ลองถามมาได้เลย!',
  },
  {
    id: 'help_navigation',
    keywords: ['ใช้งานยังไง', 'ใช้ยังไง', 'หน้าไหน', 'เมนู', 'how to use', 'navigate', 'มีหน้าอะไรบ้าง'],
    respond: (_question, ctx) => {
      const isViewer = ctx.role === 'viewer'
      const lines = [
        '• Forecast — กราฟพยากรณ์การผลิตไฟ เทียบกับของจริง ดูได้ทั้งรายวัน/รายชั่วโมง',
        ...(isViewer
          ? []
          : [
              '• Simulation — ทดลองสถานการณ์สมมติ เช่น เมฆเยอะขึ้น หรือแผงเสื่อมสภาพ',
              '• Financial — วิเคราะห์ความคุ้มค่าการลงทุน (NPV/IRR/คืนทุน)',
            ]),
        '• 3D View — ดูโรงงานจำลอง 3 มิติ พร้อมเงาและเส้นทางดวงอาทิตย์',
        '• Energy Report — รายงานสรุปพลังงานรายปี/รายเดือน',
        '• Irradiance Map — แผนที่ความเข้มแสงอาทิตย์ในพื้นที่',
      ]
      const intro = isViewer ? `เว็บนี้มี ${lines.length} หน้าที่ผู้ชมทั่วไปดูได้ครับ:` : `เว็บนี้มี ${lines.length} หน้าหลักครับ:`
      const viewerNote = isViewer ? '\n(Simulation กับ Financial เปิดให้เฉพาะบัญชี operator ขึ้นไปครับ)' : ''
      return `${intro}\n${lines.join('\n')}${viewerNote}`
    },
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
      'ยิ่งค่าสูง (เช่นเที่ยงวันฟ้าใส ~800-1000 W/m²) แผงโซลาร์ก็ยิ่งผลิตไฟได้มากขึ้นครับ',
  },
  {
    id: 'knowledge_kwp',
    keywords: ['kwp คือ', 'kwp หมายถึง', 'what is kwp'],
    respond: () =>
      'kWp (กิโลวัตต์พีค) คือกำลังการผลิตสูงสุดของแผงโซลาร์ วัดภายใต้สภาวะทดสอบมาตรฐาน (STC: แสง 1000 W/m², อุณหภูมิ 25°C) ' +
      'ส่วน kW AC คือกำลังไฟฟ้ากระแสสลับสูงสุดที่อินเวอร์เตอร์แปลงออกมาได้จริง ซึ่งมักจะน้อยกว่า kWp เล็กน้อยครับ',
  },
  {
    id: 'knowledge_plant_factor',
    keywords: ['plant factor คือ', 'solar plant factor', 'capacity factor'],
    respond: () =>
      '"Solar plant factor" (หรือ capacity factor) บอกว่าโรงไฟฟ้าผลิตไฟได้กี่เปอร์เซ็นต์ของกำลังการผลิตติดตั้งเทียบกับถ้าผลิตเต็มกำลังตลอด 24 ชม. ' +
      'โซลาร์ผลิตได้แค่ตอนกลางวัน ค่านี้จึงมักอยู่ราว 0.1-0.25 เป็นเรื่องปกติ ไม่ใช่ตัวเลขที่ต่ำผิดปกติครับ',
  },
  {
    id: 'knowledge_forecast_horizon',
    keywords: ['day-ahead', 'intra-day', 'ต่างกันยังไง', 'minute-ahead'],
    respond: () =>
      'พยากรณ์ในเว็บนี้มี 3 ระยะ: Day-ahead (พยากรณ์ล่วงหน้าหลายวัน เหมาะกับวางแผนระยะกลาง), ' +
      'Intra-day (ล่วงหน้า 1-6 ชม. แม่นกว่าเพราะใกล้เวลาจริง), และ Minute-ahead (ล่วงหน้า 10-60 นาที ' +
      'สำหรับการเปลี่ยนแปลงเร็วๆ เช่นเมฆบัง) ครับ',
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
      return `${label} กำลังผลิตไฟอยู่ประมาณ ${totalKw.toFixed(1)} kW ในขณะนี้ครับ (คำนวณจากแบบจำลอง ไม่ใช่ค่าที่วัดจากมิเตอร์จริง)`
    },
  },
  {
    id: 'today_energy',
    keywords: ['วันนี้ผลิตไฟ', 'สะสมวันนี้', 'พลังงานวันนี้', 'today energy', 'kwh วันนี้', 'ผลิตไฟได้เท่าไหร่'],
    respond: async (question, ctx) => {
      const { label, totals } = await fetchZonePerformance(extractZone(question), ctx.token)
      const totalKwh = sumField(totals, 'ac_energy_kwh_today')
      return `${label} ผลิตไฟสะสมตั้งแต่เที่ยงคืนถึงตอนนี้ประมาณ ${totalKwh.toFixed(1)} kWh ครับ (คำนวณจากแบบจำลอง ยังไม่ใช่มิเตอร์จริง - ดูรายละเอียดที่หน้า Forecast ได้ครับ)`
    },
  },
  {
    id: 'forecast',
    keywords: ['พยากรณ์', 'forecast', 'พรุ่งนี้', 'ทำนาย'],
    respond: async (question, ctx) => {
      const zone = extractZone(question) ?? 'GIS'
      const result = await getForecast(zone, 'day', ctx.token)
      const first = result.points[0]
      if (!first) return `ยังไม่มีข้อมูลพยากรณ์สำหรับ ${zone} ในตอนนี้ครับ`
      const sourceNote = result.data_source === 'real' ? 'อิงจากข้อมูลอากาศจริง' : 'ยังใช้ข้อมูลจำลอง (ข้อมูลจริงสะสมไม่พอ)'
      return (
        `พยากรณ์การผลิตไฟของ ${zone} ในช่วงถัดไป อยู่ที่ประมาณ ${first.pred.toFixed(1)} kW ` +
        (first.lower != null && first.upper != null ? `(ช่วง ${first.lower.toFixed(1)}-${first.upper.toFixed(1)} kW) ` : '') +
        `${sourceNote}ครับ - ดูกราฟเต็มได้ที่หน้า Forecast`
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
      return `กำลังการผลิตติดตั้งของโรงไฟฟ้า:\n${lines.join('\n')}\nรวมทั้งหมด ${total} kW AC ครับ`
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
      return `ตอนนี้อุณหภูมิที่โรงไฟฟ้าประมาณ ${nearest.temp_c.toFixed(1)}°C (${sourceNote}) ครับ ดูแถบอุณหภูมิเต็มได้ที่หน้า Forecast`
    },
  },
  {
    id: 'financial_info',
    keywords: ['การเงิน', 'ลงทุน', 'คืนทุน', 'roi', 'npv', 'irr', 'financial', 'คุ้มไหม'],
    respond: (_question, ctx) =>
      ctx.role === 'viewer'
        ? 'หน้า Financial (วิเคราะห์ความคุ้มค่าการลงทุน) เปิดให้เฉพาะบัญชี operator ขึ้นไปครับ บัญชีผู้ชมทั่วไปยังเข้าดูหน้านี้ไม่ได้ครับ'
        : 'หน้า Financial คำนวณความคุ้มค่าการลงทุน (NPV/IRR/LCOE/ระยะเวลาคืนทุน) ให้ครับ ' +
          'แต่ตอนนี้ตัวเลขต้นทุน/ค่าไฟ/อัตราดอกเบี้ยยังเป็นค่าประมาณเบื้องต้น ยังไม่ใช่ตัวเลขจริงของโครงการนี้ ' +
          'ลองเข้าไปปรับตัวเลขเองที่หน้า Financial ได้เลยครับ',
  },
]

// One intent per guided sub-question (see assistantTopics.ts) - generated
// rather than hand-written so adding a new topic is just: one entry in
// TOPIC_CATEGORIES + one answer in assistantContent.ts, no touching this
// file. Each keyword is the sub-question's own full question text, which
// combined with the longest-match-wins rule below guarantees clicking a
// menu button always resolves back to its own answer, never an unrelated
// hand-written intent that happens to share a short substring (e.g. "หน้า
// Forecast ในเว็บนี้ใช้ดูอะไรได้บ้าง" must win over the bare 'forecast'
// keyword on the live-data-fetching 'forecast' intent above).
const TOPIC_INTENTS: AssistantIntent[] = TOPIC_CATEGORIES.flatMap((category) =>
  category.groups.flatMap((group) =>
    group.subQuestions.map((sq): AssistantIntent => ({
      id: sq.id,
      keywords: [sq.question.toLowerCase()],
      respond: () => TOPIC_ANSWERS[sq.id] ?? ASSISTANT_FALLBACK_MESSAGE,
    })),
  ),
)

export const ASSISTANT_INTENTS: AssistantIntent[] = [...HAND_WRITTEN_INTENTS, ...TOPIC_INTENTS]

export const ASSISTANT_FALLBACK_MESSAGE =
  'ขอโทษด้วยครับ ผมยังไม่เข้าใจคำถามนี้ 🙏 ตอนนี้ผมตอบได้เฉพาะคำถามเกี่ยวกับ: การใช้งานเว็บ, ข้อมูลกำลังไฟ/พลังงานจริงในระบบ, ' +
  'พยากรณ์, และความรู้ทั่วไปเรื่องโซลาร์เซลล์ ลองเลือกหมวดด้านล่างนี้ดู หรือถามใหม่อีกครั้งได้ไหมครับ?'

const FETCH_ERROR_MESSAGE = 'ขอโทษด้วยครับ ดึงข้อมูลไม่สำเร็จตอนนี้ ลองใหม่อีกครั้งได้ไหมครับ?'

export type AssistantMood = 'happy' | 'sad'

/** A button offered alongside an assistant reply so the conversation always
 * has an obvious next step - 'question' sends its text through the normal
 * pipeline exactly like typing it; 'category'/'group'/'categories' are pure
 * client-side menu navigation (AssistantPanel.tsx), no network round-trip. */
export type AssistantOption =
  | { kind: 'categories'; label: string }
  | { kind: 'category'; label: string; categoryId: string }
  | { kind: 'group'; label: string; groupId: string }
  | { kind: 'question'; label: string; question: string }

export const TOP_LEVEL_OPTIONS: AssistantOption[] = TOPIC_CATEGORIES.map((c) => ({
  kind: 'category',
  label: `${c.emoji} ${c.title}`,
  categoryId: c.id,
}))

/** After answering a guided topic sub-question, suggest its siblings (same
 * group) as one-tap follow-ups, plus a way back to the top-level menu - so
 * asking a second/third question never requires typing from scratch. For
 * hand-written (non-topic) intents there's no group to draw siblings from,
 * so just offer the 3 top-level categories instead. */
function suggestionOptions(intentId: string): AssistantOption[] {
  const group = findGroupBySubQuestionId(intentId)
  if (!group) return TOP_LEVEL_OPTIONS
  const siblings = group.subQuestions.filter((sq) => sq.id !== intentId)
  return [
    ...siblings.map((sq): AssistantOption => ({ kind: 'question', label: sq.label, question: sq.question })),
    { kind: 'categories', label: '📚 ดูหมวดคำถามอื่น' },
  ]
}

export interface AssistantReply {
  text: string
  mood: AssistantMood
  options?: AssistantOption[]
}

/** Picks the intent whose matching keyword is *longest* (most specific),
 * not just the first one found - a short generic keyword like 'forecast'
 * on a live-data intent must lose to a long, specific menu-button question
 * like "หน้า Forecast ในเว็บนี้ใช้ดูอะไรได้บ้าง" that happens to contain it. */
function bestMatchingIntent(question: string): AssistantIntent | null {
  const lower = question.toLowerCase()
  let best: AssistantIntent | null = null
  let bestKeywordLength = -1
  for (const intent of ASSISTANT_INTENTS) {
    for (const kw of intent.keywords) {
      if (kw.length > bestKeywordLength && lower.includes(kw)) {
        best = intent
        bestKeywordLength = kw.length
      }
    }
  }
  return best
}

/** Same matching as answerQuestion(), but also reports whether น้อง Solar
 * actually understood the question - AssistantPanel.tsx uses this to set
 * the mascot's facial expression (a real match = happy, a fallback/fetch
 * failure = sad), without answerQuestion()'s own plain-string contract
 * (and every existing caller/test of it) having to change. Also returns
 * `options` (follow-up buttons) so the conversation can keep going with a
 * tap instead of the visitor having to type a brand new question every time.
 */
export async function answerQuestionWithMood(question: string, ctx: AssistantContext): Promise<AssistantReply> {
  const intent = bestMatchingIntent(question)
  if (intent) {
    try {
      const text = await intent.respond(question, ctx)
      return { text, mood: 'happy', options: suggestionOptions(intent.id) }
    } catch {
      return { text: FETCH_ERROR_MESSAGE, mood: 'sad', options: TOP_LEVEL_OPTIONS }
    }
  }

  // Nothing matched a specific question - but a bare keyword (e.g. someone
  // just typing "inverter") may still name a recognizable topic. Rather
  // than guess which of several possible questions they meant, offer a
  // clarifying menu of that topic's actual sub-questions.
  const clarifyGroup = findClarifyGroup(question)
  if (clarifyGroup) {
    return {
      text: `เรื่อง "${clarifyGroup.title}" อยากรู้แบบไหนครับ เลือกได้เลย:`,
      mood: 'happy',
      options: clarifyGroup.subQuestions.map((sq) => ({ kind: 'question', label: sq.label, question: sq.question })),
    }
  }

  return { text: ASSISTANT_FALLBACK_MESSAGE, mood: 'sad', options: TOP_LEVEL_OPTIONS }
}

/** Finds the best-matching intent (by keyword substring, longest match
 * wins) and runs it, falling back to ASSISTANT_FALLBACK_MESSAGE if nothing
 * matches or the matched intent's own data fetch fails. */
export async function answerQuestion(question: string, ctx: AssistantContext): Promise<string> {
  return (await answerQuestionWithMood(question, ctx)).text
}
