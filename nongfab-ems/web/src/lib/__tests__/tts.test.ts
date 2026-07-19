import { beforeEach, describe, expect, it, vi } from 'vitest'
import { segmentByLanguage, speakText } from '../tts'

class FakeUtterance {
  text: string
  lang = ''
  rate = 1
  voice: SpeechSynthesisVoice | null = null
  constructor(text: string) {
    this.text = text
  }
}

function fakeVoice(name: string, lang: string): SpeechSynthesisVoice {
  return { name, lang } as SpeechSynthesisVoice
}

function stubSynth(voices: SpeechSynthesisVoice[] = []) {
  const listeners: Record<string, (() => void)[]> = {}
  const synth = {
    speak: vi.fn(),
    cancel: vi.fn(),
    getVoices: vi.fn(() => voices),
    addEventListener: vi.fn((event: string, cb: () => void) => {
      listeners[event] = [...(listeners[event] ?? []), cb]
    }),
  }
  vi.stubGlobal('speechSynthesis', synth)
  vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)
  return synth
}

describe('segmentByLanguage', () => {
  it('keeps a pure-Thai string as a single Thai segment', () => {
    expect(segmentByLanguage('สวัสดีครับ')).toEqual([{ text: 'สวัสดีครับ', lang: 'th-TH' }])
  })

  it('keeps a pure-English string as a single English segment', () => {
    expect(segmentByLanguage('Hello there')).toEqual([{ text: 'Hello there', lang: 'en-US' }])
  })

  it('splits mixed Thai/English into alternating same-script runs', () => {
    expect(segmentByLanguage('หน้า Forecast ใช้งานง่าย')).toEqual([
      { text: 'หน้า ', lang: 'th-TH' },
      { text: 'Forecast ', lang: 'en-US' },
      { text: 'ใช้งานง่าย', lang: 'th-TH' },
    ])
  })

  it('keeps mid-string digits/units attached to the run before them rather than splitting out a separate segment', () => {
    const segments = segmentByLanguage('กำลังผลิตไฟอยู่ประมาณ 12.5 kW ครับ')
    expect(segments).toEqual([
      { text: 'กำลังผลิตไฟอยู่ประมาณ 12.5 ', lang: 'th-TH' },
      { text: 'kW ', lang: 'en-US' },
      { text: 'ครับ', lang: 'th-TH' },
    ])
  })

  it('holds leading digits at the very start of the text over for whichever script appears first', () => {
    expect(segmentByLanguage('12.5 kW')).toEqual([{ text: '12.5 kW', lang: 'en-US' }])
  })

  it('defaults a number-only string with no script at all to Thai', () => {
    expect(segmentByLanguage('12345')).toEqual([{ text: '12345', lang: 'th-TH' }])
  })

  it('does not emit empty/whitespace-only segments', () => {
    expect(segmentByLanguage('   ')).toEqual([])
    expect(segmentByLanguage('')).toEqual([])
  })
})

describe('speakText', () => {
  beforeEach(() => {
    stubSynth()
  })

  it('speaks a pure-Thai reply as a single th-TH utterance at the slowed clarity rate', () => {
    const synth = window.speechSynthesis as unknown as { speak: ReturnType<typeof vi.fn> }
    speakText('สวัสดีครับ')
    expect(synth.speak).toHaveBeenCalledTimes(1)
    const utterance = synth.speak.mock.calls[0][0] as FakeUtterance
    expect(utterance.text).toBe('สวัสดีครับ')
    expect(utterance.lang).toBe('th-TH')
    expect(utterance.rate).toBeLessThan(1)
  })

  it('queues a separate utterance per language run for mixed Thai/English text, each tagged with its own lang', () => {
    const synth = window.speechSynthesis as unknown as { speak: ReturnType<typeof vi.fn> }
    speakText('หน้า Forecast ใช้งานง่าย')
    expect(synth.speak).toHaveBeenCalledTimes(3)
    const calls = synth.speak.mock.calls.map((call) => {
      const u = call[0] as FakeUtterance
      return { text: u.text, lang: u.lang }
    })
    expect(calls).toEqual([
      { text: 'หน้า ', lang: 'th-TH' },
      { text: 'Forecast ', lang: 'en-US' },
      { text: 'ใช้งานง่าย', lang: 'th-TH' },
    ])
  })

  it('cancels any speech already in progress/queued before speaking, so rapid clicks never stack a backlog', () => {
    const synth = window.speechSynthesis as unknown as { cancel: ReturnType<typeof vi.fn>; speak: ReturnType<typeof vi.fn> }
    speakText('ข้อความแรก')
    speakText('ข้อความที่สอง')
    expect(synth.cancel).toHaveBeenCalledTimes(2)
  })

  it('does not throw when speechSynthesis is unavailable', () => {
    vi.stubGlobal('speechSynthesis', undefined)
    expect(() => speakText('สวัสดีครับ')).not.toThrow()
  })

  it('prefers a Google-branded voice for the language over a plain system one, when both exist', () => {
    const googleVoice = fakeVoice('Google ไทย', 'th-TH')
    const systemVoice = fakeVoice('Kanya', 'th-TH')
    const synth = stubSynth([systemVoice, googleVoice])
    speakText('สวัสดีครับ')
    const utterance = synth.speak.mock.calls[0][0] as FakeUtterance
    expect(utterance.voice).toBe(googleVoice)
  })

  it('falls back to any voice matching the language when no Google voice is installed', () => {
    const onlySystemVoice = fakeVoice('Kanya', 'th-TH')
    const synth = stubSynth([onlySystemVoice])
    speakText('สวัสดีครับ')
    const utterance = synth.speak.mock.calls[0][0] as FakeUtterance
    expect(utterance.voice).toBe(onlySystemVoice)
  })

  it('leaves voice unset (browser default) when getVoices returns nothing', () => {
    const synth = stubSynth([])
    speakText('สวัสดีครับ')
    const utterance = synth.speak.mock.calls[0][0] as FakeUtterance
    expect(utterance.voice).toBeNull()
  })

  it('picks the matching voice independently per language segment in a mixed-language reply', () => {
    const thaiVoice = fakeVoice('Google ไทย', 'th-TH')
    const englishVoice = fakeVoice('Google US English', 'en-US')
    const synth = stubSynth([thaiVoice, englishVoice])
    speakText('หน้า Forecast ใช้งานง่าย')
    const voicesUsed = synth.speak.mock.calls.map((call) => (call[0] as FakeUtterance).voice)
    expect(voicesUsed).toEqual([thaiVoice, englishVoice, thaiVoice])
  })
})
