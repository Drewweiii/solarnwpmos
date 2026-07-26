/** Listening, the half of the conversation น้อง Solar never had (2026-07-26).
 *
 * `tts.ts` already speaks and `assistant.ts` already understands typed
 * questions; the only missing piece was hearing one. This is that piece, and
 * nothing else - the recognised text goes straight into the SAME
 * `ASSISTANT_INTENTS` matcher a typed question uses, so there is no second
 * brain to keep in sync and no answer that voice can give but typing cannot.
 *
 * Same rules `tts.ts` set for this project:
 *   * Browser-native (`SpeechRecognition`), no API key, no server round-trip -
 *     the zero-cost-API rule.
 *   * A no-op, never an error, where it is unavailable. Firefox has no
 *     SpeechRecognition at all and Safari's is partial, so the mic button has
 *     to disappear rather than sit there doing nothing when clicked.
 *
 * PUSH-TO-TALK, never an open mic. Holding the microphone open would be worse
 * on three counts at once - privacy (a public-facing dashboard listening
 * continuously), battery, and accuracy (every passing conversation becomes a
 * question). The visitor presses, speaks, and it stops on its own.
 */

// The constructor is vendor-prefixed on Chromium and absent on Firefox, so it
// is reached through the window rather than a DOM lib type.
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function recognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function isSpeechRecognitionSupported(): boolean {
  return recognitionCtor() !== null
}

/** Thai speech recognition transcribes English technical terms phonetically,
 * and `bestMatchingIntent` matches on literal substrings - so "เคดับเบิลยูพี"
 * never reaches the `kwp` intent no matter how clearly it was said.
 *
 * Each entry below is a term that appears in a real intent's keyword list (see
 * ASSISTANT_INTENTS / assistantTopics), spelled the way Thai TTS-grade speech
 * recognition actually renders it. Deliberately small: this is a bridge for
 * terms the matcher already knows, not a general-purpose Thai-English
 * dictionary, and every line here is a claim that a specific keyword would
 * otherwise be unreachable by voice.
 */
const SPOKEN_TERM_FIXES: ReadonlyArray<readonly [RegExp, string]> = [
  [/เคดับเบิ?ล(ยู|ลิว)พี/g, 'kWp'],
  [/กิโลวัตต์พีค/g, 'kWp'],
  [/เดย์?\s*อะเฮด|เดย์\s*เฮด/g, 'day-ahead'],
  [/อินทรา\s*เดย์|อินตร้า\s*เดย์/g, 'intra-day'],
  [/มินิต\s*อะเฮด|มินิท\s*อะเฮด/g, 'minute-ahead'],
  [/เอ็นพีวี/g, 'NPV'],
  [/ไออาร์อาร์/g, 'IRR'],
  [/แอลซีโอดี|แอลซีโออี/g, 'LCOE'],
  [/อาร์โอไอ/g, 'ROI'],
  [/พลานท์\s*แฟกเตอร์|แพลนท์\s*แฟคเตอร์/g, 'plant factor'],
  [/ฟอร์แคสท?/g, 'forecast'],
  [/กฟผ\.?/g, 'EGAT'],
]

/** Clean up one recognised utterance before handing it to the intent matcher.
 *
 * Also strips the trailing question marks and full stops some engines add:
 * harmless for matching (which uses `includes`), but they show up in the chat
 * transcript as if the speaker had said them.
 */
export function normalizeSpokenQuestion(raw: string): string {
  let text = raw.trim()
  for (const [pattern, replacement] of SPOKEN_TERM_FIXES) {
    text = text.replace(pattern, replacement)
  }
  // Collapse the runs of whitespace that phrase-by-phrase engines leave behind.
  return text.replace(/\s+/g, ' ').trim()
}

export interface SpeechListenerHandlers {
  /** Fires repeatedly with the best-guess text so far, so the input box can
   * show words appearing as they are spoken. Already normalized. */
  onInterim?: (text: string) => void
  /** Fires once with the final utterance. Already normalized. */
  onFinal: (text: string) => void
  /** Fires on failure OR on a silent recording. `reason` is the browser's own
   * error string where there is one ("not-allowed" when the visitor denied the
   * mic, "no-speech" when nothing was heard). */
  onError?: (reason: string) => void
  /** Fires when the session ends for any reason, success or not - the caller
   * uses it to drop the "listening" state rather than tracking three paths. */
  onEnd?: () => void
}

export interface SpeechListener {
  start: () => void
  stop: () => void
}

/** Build a one-utterance listener, or null where the browser cannot.
 *
 * Returning null rather than a throwing stub is deliberate: the caller's
 * correct response is to not render a microphone at all, and a null is
 * impossible to render by accident.
 */
export function createSpeechListener(
  handlers: SpeechListenerHandlers,
  lang = 'th-TH',
): SpeechListener | null {
  const Ctor = recognitionCtor()
  if (!Ctor) return null

  const recognition = new Ctor()
  recognition.lang = lang
  // One utterance per press - see the module docstring on why the mic is never
  // left open.
  recognition.continuous = false
  recognition.interimResults = true
  recognition.maxAlternatives = 1

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      const text = normalizeSpokenQuestion(result[0]?.transcript ?? '')
      if (!text) continue
      if (result.isFinal) handlers.onFinal(text)
      else handlers.onInterim?.(text)
    }
  }
  recognition.onerror = (event) => handlers.onError?.(event.error ?? 'unknown')
  recognition.onend = () => handlers.onEnd?.()

  return {
    start: () => {
      try {
        recognition.start()
      } catch {
        // Chrome throws InvalidStateError if start() is called while already
        // running - a double-tap on the button, not a real failure. Swallowed
        // so a fast second press cannot break the session that is already live.
      }
    },
    stop: () => recognition.stop(),
  }
}

/** What to tell the visitor when recognition fails. The browser's raw error
 * codes are meaningless to a site visitor, and "not-allowed" in particular
 * needs to explain itself - it means they denied the microphone, which is not
 * a malfunction and should not read like one. */
export function speechErrorMessage(reason: string): string {
  if (reason === 'not-allowed' || reason === 'service-not-allowed') {
    return 'ยังไม่ได้อนุญาตให้ใช้ไมโครโฟนครับ — กดอนุญาตในเบราว์เซอร์แล้วลองใหม่ได้เลย'
  }
  if (reason === 'no-speech') return 'ผมยังไม่ได้ยินเสียงเลยครับ ลองกดแล้วพูดอีกครั้งได้ไหม'
  if (reason === 'audio-capture') return 'หาไมโครโฟนไม่เจอครับ ลองตรวจว่าเครื่องมีไมค์และไม่ได้ถูกปิดอยู่'
  if (reason === 'network') return 'การรู้จำเสียงต้องต่อเน็ตครับ ตอนนี้เชื่อมต่อไม่ได้'
  return 'ฟังไม่ชัดครับ ลองพูดอีกครั้งได้ไหม'
}
