/** Stickers for the visitor chat (VisitorNetwork.tsx) - original emoji +
 * Thai-caption combos, not a reproduction of any licensed sticker set (e.g.
 * LINE's official characters) - those are copyrighted artwork this project
 * has no rights to redistribute. Each one plays its caption aloud via the
 * browser's free, built-in Web Speech API (`speechSynthesis`) when it
 * arrives live - no paid TTS/voice API involved, consistent with this
 * project's zero-cost-API rule. Quality depends entirely on whichever Thai
 * system voice (if any) the visitor's own browser/OS ships; there's no way
 * to guarantee a specific voice from client-side JS.
 *
 * Encoding: a sticker message is just a specially-prefixed string sent
 * through the exact same `text` field/WebSocket path as a normal chat
 * message (see ws_chat.py) - the backend stores/broadcasts it as opaque
 * text with no changes needed there at all. `decodeSticker()` is what turns
 * that back into a renderable sticker on the receiving end.
 */

export interface StickerOption {
  id: string
  emoji: string
  label: string
  color: string
}

export const STICKER_OPTIONS: StickerOption[] = [
  { id: 'hello', emoji: '👋', label: 'สวัสดี', color: '#FDE68A' },
  { id: 'thanks', emoji: '🙏', label: 'ขอบคุณ', color: '#FEF3C7' },
  { id: 'fight', emoji: '💪', label: 'สู้ๆ', color: '#BFDBFE' },
  { id: 'love', emoji: '❤️', label: 'รักนะ', color: '#FBCFE8' },
  { id: 'bad', emoji: '😣', label: 'แย่จัง', color: '#FCA5A5' },
  { id: 'laugh', emoji: '😂', label: 'ฮ่าๆ', color: '#FEF08A' },
  { id: 'congrats', emoji: '🎉', label: 'ยินดีด้วย', color: '#A7F3D0' },
  { id: 'ok', emoji: '👍', label: 'โอเค', color: '#BAE6FD' },
]

const STICKER_PREFIX = '::sticker::'

export function encodeSticker(id: string): string {
  return `${STICKER_PREFIX}${id}`
}

export function decodeSticker(text: string): StickerOption | null {
  if (!text.startsWith(STICKER_PREFIX)) return null
  const id = text.slice(STICKER_PREFIX.length)
  return STICKER_OPTIONS.find((s) => s.id === id) ?? null
}

/** Speaks a sticker's Thai caption aloud via the browser's built-in
 * speechSynthesis - a no-op (not an error) on a browser/environment where
 * it isn't available (e.g. the jsdom test environment, or a browser with no
 * Thai voice installed at all). */
export function speakSticker(sticker: StickerOption): void {
  if (typeof window === 'undefined') return
  const synth = window.speechSynthesis
  if (!synth) return
  const utterance = new SpeechSynthesisUtterance(sticker.label)
  utterance.lang = 'th-TH'
  synth.speak(utterance)
}
