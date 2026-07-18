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
 */
export function speakText(text: string): void {
  if (typeof window === 'undefined') return
  const synth = window.speechSynthesis
  if (!synth) return
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'th-TH'
  synth.speak(utterance)
}
