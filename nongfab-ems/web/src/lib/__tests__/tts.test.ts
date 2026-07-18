import { beforeEach, describe, expect, it, vi } from 'vitest'
import { speakText } from '../tts'

describe('speakText', () => {
  beforeEach(() => {
    vi.stubGlobal('speechSynthesis', { speak: vi.fn(), cancel: vi.fn() })
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

  it('speaks the given text in Thai', () => {
    speakText('สวัสดีครับ')
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1)
    const utterance = (window.speechSynthesis.speak as ReturnType<typeof vi.fn>).mock.calls[0][0] as SpeechSynthesisUtterance
    expect(utterance.text).toBe('สวัสดีครับ')
    expect(utterance.lang).toBe('th-TH')
  })

  it('cancels any speech already in progress/queued before speaking, so rapid clicks never stack a backlog', () => {
    speakText('ข้อความแรก')
    speakText('ข้อความที่สอง')
    expect(window.speechSynthesis.cancel).toHaveBeenCalledTimes(2)
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2)
  })

  it('does not throw when speechSynthesis is unavailable', () => {
    vi.stubGlobal('speechSynthesis', undefined)
    expect(() => speakText('สวัสดีครับ')).not.toThrow()
  })
})
