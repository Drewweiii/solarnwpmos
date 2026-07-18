import { useCallback, useEffect, useRef, useState } from 'react'
import type { MascotMood } from '../components/MascotFace'

const DEFAULT_DURATION_MS = 5000

export interface MascotReactionState {
  mood: MascotMood
  /** Speech-bubble text, or null when nothing should be shown. Only ever
   * set together with a mood change (see trigger()). */
  speech: string | null
  /** Fire a reaction: face changes to `mood`, optionally shows `speech` in a
   * bubble, both revert to idle/null after `durationMs`.
   *
   * The critical property here (per the user's explicit 2026-07-18 request
   * - "กดหลายๆ ครั้งห้าม stack นะ เช่นลูบหัว 10 ครั้ง ห้ามกลายเป็นรอ 50
   * วินาที"): every call clears whatever timer is currently pending and
   * starts a brand new one, unconditionally - including when `mood`/`speech`
   * happen to be identical to what's already showing. A naive
   * `useEffect(() => {...}, [mood])` approach would NOT do this, because
   * React bails out of re-running an effect when a dependency's value
   * doesn't actually change (calling setState with the same value is a
   * no-op) - so clicking the same interaction twice in a row wouldn't reset
   * the clock and could look like it "stuck". Managing the timer imperatively
   * with a ref inside the callback itself, instead of via a dependency-
   * driven effect, is what guarantees a rapid burst of clicks always ends
   * exactly `durationMs` after the *last* one, never later.
   */
  trigger: (mood: MascotMood, speech?: string | null, durationMs?: number) => void
}

/** Owns น้อง Solar's current facial expression + speech bubble, shared by
 * both the AI assistant's own answer-driven mood (happy/sad, no bubble) and
 * the "เล่นกับน้อง Solar" play interactions (any mood, with a bubble) - see
 * AIAssistant.tsx, which is the single owner of one of these per app
 * instance, threaded down to both the floating Mascot button and
 * AssistantPanel's play buttons. */
export function useMascotReaction(): MascotReactionState {
  const [mood, setMood] = useState<MascotMood>('idle')
  const [speech, setSpeech] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const trigger = useCallback((newMood: MascotMood, newSpeech: string | null = null, durationMs: number = DEFAULT_DURATION_MS) => {
    clearTimeout(timerRef.current)
    setMood(newMood)
    setSpeech(newSpeech)
    timerRef.current = setTimeout(() => {
      setMood('idle')
      setSpeech(null)
    }, durationMs)
  }, [])

  useEffect(() => () => clearTimeout(timerRef.current), [])

  return { mood, speech, trigger }
}
