import type { MascotMood } from '../components/MascotFace'

export interface MascotInteraction {
  id: string
  /** Button label shown in the "เล่นกับน้อง Solar" panel (AssistantPanel.tsx). */
  label: string
  mood: MascotMood
  /** Speech-bubble line, shown next to the mascot for ~5s (see
   * useMascotReaction.ts) - always in character (ผม/ครับ, never หนู/ค่ะ/คะ),
   * same voice as every other line น้อง Solar speaks anywhere in the app. */
  speech: string
}

/** "เล่นกับน้อง Solar" - a standalone playful feature the user explicitly
 * asked to sit alongside the site's engineering/data content as its own
 * highlight (2026-07-18): a bunch of cute, harmless things a visitor can do
 * to the mascot from right inside the AI assistant panel (no separate page/
 * tab needed), each with its own reaction face + a short line of dialogue.
 * Kept deliberately generous ("ขอเยอะๆ เลยนะ") rather than 2-3 token options.
 */
export const MASCOT_INTERACTIONS: MascotInteraction[] = [
  { id: 'pet_head', label: '🤚 ลูบหัว', mood: 'blush', speech: 'ขอบคุณค้าบบ~ 😳' },
  { id: 'poke', label: '👉 จิ้มแก้ม', mood: 'hurt', speech: 'อย่าจิ้มเค้าาา!' },
  { id: 'hold_hands', label: '🤝 จับมือ', mood: 'blush', speech: 'อุ่นใจจังเลยครับ 🥹' },
  { id: 'tickle', label: '🪶 จั๊กจี้', mood: 'laugh', speech: 'ฮ่าๆๆ จั๊กจี้อ่ะ หยุดเลยครับ!' },
  { id: 'rain', label: '🌧️ ทำฝนตกใส่', mood: 'wet', speech: 'โอ๊ย เปียกหมดเลยครับ ☔' },
  { id: 'hug', label: '🤗 กอด', mood: 'love', speech: 'กอดอุ่นๆ แบบนี้ชอบเลยครับ 🥰' },
  { id: 'feed', label: '🍦 ป้อนไอติม', mood: 'excited', speech: 'หวานอร่อยจัง ขอบคุณครับ!' },
  { id: 'cheer', label: '📣 เชียร์', mood: 'excited', speech: 'ขอบคุณที่เชียร์ผมนะครับ! 💪' },
  { id: 'surprise', label: '🎉 จู่ๆ ก็ทัก', mood: 'surprised', speech: 'ว้าย! ตกใจหมดเลยครับ' },
  { id: 'pinch_cheek', label: '🤏 บีบแก้ม', mood: 'blush', speech: 'แก้มม แก้มม~ เจ็บนิดนึงนะครับ' },
  { id: 'flower', label: '🌸 มอบดอกไม้', mood: 'love', speech: 'ขอบคุณดอกไม้สวยๆ นะครับ 🌸' },
  { id: 'highfive', label: '✋ ไฮไฟว์', mood: 'happy', speech: 'เย้ ไฮไฟว์ครับ!' },
]

export function findMascotInteraction(id: string): MascotInteraction | null {
  return MASCOT_INTERACTIONS.find((i) => i.id === id) ?? null
}
