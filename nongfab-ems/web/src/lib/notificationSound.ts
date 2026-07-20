/** A tiny two-note "ding" for incoming chat messages, synthesized with the
 * Web Audio API - no audio asset to ship or load. Wrapped in try/catch and
 * silently skipped when the browser blocks audio (autoplay policy before any
 * user gesture, jsdom in tests, etc.) - a missed ding must never break the
 * message delivery it decorates. */

let ctx: AudioContext | null = null

export function playNotificationDing(): void {
  try {
    ctx = ctx ?? new AudioContext()
    if (ctx.state === 'suspended') void ctx.resume()
    const t = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    // A5 -> D6: a soft, cheerful "someone's here" chime.
    osc.frequency.setValueAtTime(880, t)
    osc.frequency.setValueAtTime(1174.66, t + 0.09)
    gain.gain.setValueAtTime(0.0001, t)
    gain.gain.exponentialRampToValueAtTime(0.12, t + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.5)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(t)
    osc.stop(t + 0.55)
  } catch {
    // no audio available - fine, the visual toast/badge still notify
  }
}
