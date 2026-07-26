import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createSpeechListener,
  isSpeechRecognitionSupported,
  normalizeSpokenQuestion,
  speechErrorMessage,
} from '../speech'

/** A stand-in for the browser's SpeechRecognition, so the wiring can be tested
 * without a microphone. Mirrors only what speech.ts actually touches. */
class FakeRecognition {
  lang = ''
  continuous = true
  interimResults = false
  maxAlternatives = 0
  started = 0
  stopped = 0
  onresult: ((e: unknown) => void) | null = null
  onerror: ((e: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  throwOnStart = false

  start() {
    if (this.throwOnStart) throw new Error('InvalidStateError')
    this.started += 1
  }
  stop() {
    this.stopped += 1
  }
  abort() {}

  emit(transcript: string, isFinal: boolean) {
    const results = [Object.assign([{ transcript }], { isFinal })]
    this.onresult?.({ resultIndex: 0, results })
  }
}

function installFake(): FakeRecognition {
  const instance = new FakeRecognition()
  ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = function () {
    return instance
  }
  return instance
}

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).SpeechRecognition
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition
})

describe('isSpeechRecognitionSupported', () => {
  it('is false where the browser has no SpeechRecognition at all (Firefox)', () => {
    expect(isSpeechRecognitionSupported()).toBe(false)
  })

  it('finds the vendor-prefixed constructor too', () => {
    ;(window as unknown as Record<string, unknown>).webkitSpeechRecognition = function () {}
    expect(isSpeechRecognitionSupported()).toBe(true)
  })
})

describe('normalizeSpokenQuestion', () => {
  it('turns a phonetically transcribed technical term into the keyword the matcher knows', () => {
    // 'kWp' is a real keyword in ASSISTANT_INTENTS; "เคดับเบิลยูพี" would never
    // reach it, because the matcher compares literal substrings.
    expect(normalizeSpokenQuestion('เคดับเบิลยูพี คืออะไร')).toContain('kWp')
    expect(normalizeSpokenQuestion('เอ็นพีวี คืออะไร')).toContain('NPV')
  })

  it('repairs the horizon names, which are hyphenated keywords speech never produces', () => {
    expect(normalizeSpokenQuestion('เดย์ อะเฮด ต่างกับ อินทรา เดย์ ยังไง')).toContain('day-ahead')
    expect(normalizeSpokenQuestion('เดย์ อะเฮด ต่างกับ อินทรา เดย์ ยังไง')).toContain('intra-day')
  })

  it('collapses the whitespace phrase-by-phrase engines leave behind', () => {
    expect(normalizeSpokenQuestion('  ตอนนี้   ผลิตไฟ   เท่าไหร่  ')).toBe('ตอนนี้ ผลิตไฟ เท่าไหร่')
  })

  it('leaves an already-clean question alone', () => {
    expect(normalizeSpokenQuestion('ตอนนี้ผลิตไฟเท่าไหร่')).toBe('ตอนนี้ผลิตไฟเท่าไหร่')
  })
})

describe('createSpeechListener', () => {
  it('returns null rather than a throwing stub where unsupported', () => {
    // Null is impossible to render by accident; a stub invites a dead button.
    expect(createSpeechListener({ onFinal: () => {} })).toBeNull()
  })

  it('configures one utterance per press, never an open mic', () => {
    const fake = installFake()
    createSpeechListener({ onFinal: () => {} })
    expect(fake.continuous).toBe(false)
    expect(fake.interimResults).toBe(true)
    expect(fake.lang).toBe('th-TH')
  })

  it('reports interim text separately from the final utterance', () => {
    const fake = installFake()
    const interim: string[] = []
    const final: string[] = []
    const listener = createSpeechListener({ onInterim: (t) => interim.push(t), onFinal: (t) => final.push(t) })
    listener!.start()
    fake.emit('ตอนนี้ผลิต', false)
    fake.emit('ตอนนี้ผลิตไฟเท่าไหร่', true)
    expect(interim).toEqual(['ตอนนี้ผลิต'])
    expect(final).toEqual(['ตอนนี้ผลิตไฟเท่าไหร่'])
  })

  it('normalizes before handing the text on, so the caller never sees raw phonetics', () => {
    const fake = installFake()
    const final: string[] = []
    const listener = createSpeechListener({ onFinal: (t) => final.push(t) })
    listener!.start()
    fake.emit('เอ็นพีวี เท่าไหร่', true)
    expect(final[0]).toContain('NPV')
  })

  it('swallows the InvalidStateError a double-tap causes instead of breaking the session', () => {
    const fake = installFake()
    fake.throwOnStart = true
    const listener = createSpeechListener({ onFinal: () => {} })
    expect(() => listener!.start()).not.toThrow()
  })

  it('reports the end of a session however it ended', () => {
    const fake = installFake()
    const onEnd = vi.fn()
    createSpeechListener({ onFinal: () => {}, onEnd })
    fake.onend?.()
    expect(onEnd).toHaveBeenCalled()
  })

  it('passes the browser error code through', () => {
    const fake = installFake()
    const errors: string[] = []
    createSpeechListener({ onFinal: () => {}, onError: (r) => errors.push(r) })
    fake.onerror?.({ error: 'not-allowed' })
    expect(errors).toEqual(['not-allowed'])
  })
})

describe('speechErrorMessage', () => {
  it('explains a denied microphone as a choice, not a malfunction', () => {
    expect(speechErrorMessage('not-allowed')).toMatch(/อนุญาต/)
  })

  it('tells a silent recording apart from a broken one', () => {
    expect(speechErrorMessage('no-speech')).toMatch(/ยังไม่ได้ยินเสียง/)
    expect(speechErrorMessage('audio-capture')).toMatch(/หาไมโครโฟนไม่เจอ/)
  })

  it('falls back to something a visitor can act on for an unknown code', () => {
    expect(speechErrorMessage('weird-future-code')).toMatch(/ลองพูดอีกครั้ง/)
  })
})
