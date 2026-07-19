/** Speaks text aloud via the browser's built-in `speechSynthesis` (Web
 * Speech API) - free, no API key, no server round-trip, consistent with
 * this project's zero-cost-API rule. A no-op (not an error) wherever it's
 * unavailable (jsdom tests, a browser/OS with no Thai voice installed).
 * Quality depends entirely on whichever system voice (if any) the
 * visitor's own browser/OS ships - there's no way to guarantee a specific
 * voice from client-side JS.
 *
 * Cancels any speech already in progress/queued first, so rapid repeated
 * clicks (the 🔊 button on an AssistantPanel reply, a fast run of chat
 * stickers) can never stack up an unbounded backlog of queued utterances -
 * same no-stack principle as this session's other rapid-click fixes
 * (useMascotReaction.ts, AssistantPanel.tsx's category menu).
 *
 * Clarity pass (2026-07-18, reported live: "อยากให้ชัดเจนมากขึ้นอีกเยอะๆ" for
 * both Thai and English reading). Two independent problems, two fixes:
 *
 * 1. Every reply here is naturally mixed-language (น้อง Solar mixes Thai
 *    sentences with English technical terms - "kWp", "GIS", "Forecast",
 *    "NPV/IRR/LCOE", "Day-ahead") - forcing the whole utterance through a
 *    single `lang: 'th-TH'` voice makes a Thai TTS engine mangle every
 *    English word it hits (and the reverse would mangle the Thai). Fixed by
 *    segmenting the text into same-script runs (`segmentByLanguage`) and
 *    speaking each run with the matching `lang`, queued as separate
 *    utterances - the Web Speech API plays multiple `speak()` calls back to
 *    back in order, so this doesn't need manual chaining via `onend`.
 * 2. The default `rate` (1.0, "normal speed") reads noticeably rushed on
 *    most Thai TTS voices - slowed to 0.92, a small enough change to stay
 *    natural-sounding while giving each syllable more room.
 *
 * Voice selection: `speechSynthesis.getVoices()` can return an empty list
 * until the async `voiceschanged` event fires (Chrome in particular) - the
 * first call primes a cache and subscribes to that event so a later call
 * (e.g. a slower page load) still benefits once voices actually arrive.
 * Where more than one voice matches a language, a voice whose name mentions
 * "Google" is preferred - on Chrome these are the higher-quality
 * network-backed voices, and picking one where available is the clearest
 * win this module can make without shipping/calling a paid TTS API.
 */

const THAI_SCRIPT = /[฀-๿]/
const LATIN_LETTER = /[A-Za-z]/

export type TtsLang = 'th-TH' | 'en-US'

const SPEECH_RATE = 0.92

// Keyed by the `SpeechSynthesis` instance itself (not a bare module-level
// array) - there's only ever one real `window.speechSynthesis`, so this is
// mostly about correctness/isolation rather than actually needing to
// support several synth instances at once.
const voiceCache = new WeakMap<SpeechSynthesis, SpeechSynthesisVoice[]>()
const subscribedSynths = new WeakSet<SpeechSynthesis>()

function refreshVoiceCache(synth: SpeechSynthesis): SpeechSynthesisVoice[] {
  const voices = synth.getVoices()
  if (voices.length > 0) voiceCache.set(synth, voices)
  if (!subscribedSynths.has(synth) && 'onvoiceschanged' in synth) {
    subscribedSynths.add(synth)
    synth.addEventListener('voiceschanged', () => {
      const updated = synth.getVoices()
      if (updated.length > 0) voiceCache.set(synth, updated)
    })
  }
  return voiceCache.get(synth) ?? []
}

function pickVoice(synth: SpeechSynthesis, lang: TtsLang): SpeechSynthesisVoice | undefined {
  const voices = refreshVoiceCache(synth)
  if (voices.length === 0) return undefined
  const prefix = lang.split('-')[0]
  const matching = voices.filter((v) => v.lang === lang || v.lang.toLowerCase().startsWith(prefix))
  if (matching.length === 0) return undefined
  return matching.find((v) => /google/i.test(v.name)) ?? matching[0]
}

/** Splits text into consecutive same-script runs, tagging each with the
 * language to speak it in. Digits/punctuation/whitespace have no script of
 * their own, so they never force a split by themselves - they stay attached
 * to whichever run is already open (mid-string digits/units like "12.5 kW"
 * stay with the run before them; digits at the very start of the string,
 * before any script has appeared yet, are held over and attached to the
 * first run that does appear) rather than fragmenting into their own
 * segment, and only fall back to Thai if the text never contains a Thai or
 * Latin character at all (a plain number on its own). */
export function segmentByLanguage(text: string): { text: string; lang: TtsLang }[] {
  const raw: { text: string; lang: TtsLang }[] = []
  let current = ''
  let currentLang: TtsLang | null = null

  for (const ch of text) {
    const charLang: TtsLang | null = THAI_SCRIPT.test(ch) ? 'th-TH' : LATIN_LETTER.test(ch) ? 'en-US' : null

    if (charLang === null || charLang === currentLang) {
      current += ch
      continue
    }
    if (currentLang !== null) raw.push({ text: current, lang: currentLang })
    else if (current.trim().length > 0) raw.push({ text: current, lang: charLang }) // leading digits/punctuation before any script - fold into the run that follows
    current = ch
    currentLang = charLang
  }
  if (current.trim().length > 0) raw.push({ text: current, lang: currentLang ?? 'th-TH' })

  // Merge back-to-back same-language segments (e.g. leading digits folded
  // into the run that follows can otherwise land as its own segment right
  // next to that run) so a queued utterance doesn't leave an audible gap in
  // the middle of what should read as one phrase.
  const merged: { text: string; lang: TtsLang }[] = []
  for (const segment of raw) {
    const last = merged[merged.length - 1]
    if (last && last.lang === segment.lang) last.text += segment.text
    else merged.push({ ...segment })
  }
  return merged.filter((s) => s.text.trim().length > 0)
}

export function speakText(text: string): void {
  if (typeof window === 'undefined') return
  const synth = window.speechSynthesis
  if (!synth) return
  synth.cancel()

  for (const segment of segmentByLanguage(text)) {
    const utterance = new SpeechSynthesisUtterance(segment.text)
    utterance.lang = segment.lang
    utterance.rate = SPEECH_RATE
    const voice = pickVoice(synth, segment.lang)
    if (voice) utterance.voice = voice
    synth.speak(utterance)
  }
}
