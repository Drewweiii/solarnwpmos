import { beforeEach, describe, expect, it, vi } from 'vitest'
import { decodeSticker, encodeSticker, speakSticker, STICKER_OPTIONS } from '../stickers'

describe('sticker encode/decode', () => {
  it('round-trips every catalog sticker through encode/decode', () => {
    for (const sticker of STICKER_OPTIONS) {
      expect(decodeSticker(encodeSticker(sticker.id))).toEqual(sticker)
    }
  })

  it('returns null for plain text and for an unknown sticker id', () => {
    expect(decodeSticker('สวัสดีครับ')).toBeNull()
    expect(decodeSticker('::sticker::not-a-real-id')).toBeNull()
  })
})

describe('speakSticker', () => {
  beforeEach(() => {
    vi.stubGlobal('speechSynthesis', { speak: vi.fn(), cancel: vi.fn(), getVoices: vi.fn(() => []), addEventListener: vi.fn() })
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        text: string
        lang = ''
        constructor(text: string) {
          this.text = text
        }
      },
    )
  })

  it('speaks the sticker caption in Thai', () => {
    speakSticker(STICKER_OPTIONS[0])
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1)
    const utterance = (window.speechSynthesis.speak as ReturnType<typeof vi.fn>).mock.calls[0][0] as SpeechSynthesisUtterance
    expect(utterance.text).toBe(STICKER_OPTIONS[0].label)
    expect(utterance.lang).toBe('th-TH')
  })

  it('does not throw when speechSynthesis is unavailable', () => {
    vi.stubGlobal('speechSynthesis', undefined)
    expect(() => speakSticker(STICKER_OPTIONS[0])).not.toThrow()
  })
})
