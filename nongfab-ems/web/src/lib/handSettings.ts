import { useEffect, useMemo, useState } from 'react'
import { DEFAULT_HAND_CONTROL_CONFIG, DEFAULT_LATCH_HOLD_SECONDS, type HandControlConfig } from './handControl'
import { useSystemSettings } from './queries'
import { loadSettingsDraft, SETTINGS_DRAFT_EVENT } from './settingsDraft'
import type { SettingItem } from './types'

/** Part 3 of "editable system values" (2026-07-25): make the `hand.*` group
 * actually drive the 3D view's hand control. Parts 1 and 2 stored and edited
 * these seven values; until now `handControl`/`Solar3DScene` still used their
 * compiled-in constants, so publishing a value changed nothing on screen.
 *
 * Two sources, in order of precedence:
 *   1. this browser's local draft (what a viewer is trying right now)
 *   2. the published value from `GET /settings`
 *   3. the compiled default, if the settings request hasn't landed / failed
 *
 * Honouring the draft is deliberate and specific to this group: these settings
 * are `frontend_only` "how does it feel" tuning, and the point of letting a
 * non-admin try values is that they can feel the difference immediately.
 */

/** Everything the 3D scene needs to drive hand control, resolved from settings. */
export interface HandTuning {
  /** Gesture/mapping config consumed by `mapHandToSignal` + `detectGesture`. */
  config: HandControlConfig
  /** Camera speeds at full rate, consumed by `integrateHandCamera`. */
  azimuthSpeed: number
  polarSpeed: number
  zoomSpeed: number
  /** How long 👍 must be held before the start/stop latch fires. */
  latchHoldSeconds: number
}

export const DEFAULT_HAND_TUNING: HandTuning = {
  config: DEFAULT_HAND_CONTROL_CONFIG,
  azimuthSpeed: 2.0,
  polarSpeed: 1.1,
  zoomSpeed: 0.8,
  latchHoldSeconds: DEFAULT_LATCH_HOLD_SECONDS,
}

/** Pure resolver, exported for tests: published settings + local draft -> the
 * numbers the scene runs on. Unknown/missing keys fall back to the compiled
 * default, so an older API (or a failed request) degrades to today's feel
 * rather than to zeros. */
export function resolveHandTuning(
  settings: SettingItem[] | undefined,
  draft: Record<string, number> = {},
): HandTuning {
  const published = new Map<string, number>()
  for (const item of settings ?? []) {
    if (item.key.startsWith('hand.')) published.set(item.key, item.value)
  }
  const pick = (key: string, fallback: number): number => {
    const value = draft[key] ?? published.get(key)
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback
  }
  return {
    config: {
      ...DEFAULT_HAND_CONTROL_CONFIG,
      deadzone: pick('hand.deadzone', DEFAULT_HAND_CONTROL_CONFIG.deadzone),
      pinchEngageRatio: pick('hand.pinch_engage_ratio', DEFAULT_HAND_CONTROL_CONFIG.pinchEngageRatio),
      rateGain: pick('hand.rate_gain', DEFAULT_HAND_CONTROL_CONFIG.rateGain),
    },
    azimuthSpeed: pick('hand.azimuth_speed_rad_s', DEFAULT_HAND_TUNING.azimuthSpeed),
    polarSpeed: pick('hand.polar_speed_rad_s', DEFAULT_HAND_TUNING.polarSpeed),
    zoomSpeed: pick('hand.zoom_speed_per_s', DEFAULT_HAND_TUNING.zoomSpeed),
    latchHoldSeconds: pick('hand.latch_hold_seconds', DEFAULT_HAND_TUNING.latchHoldSeconds),
  }
}

/** The live tuning for the current browser. Re-resolves when the published
 * settings change (query refetch) or when this browser's draft is edited on
 * the settings page (same-tab custom event + cross-tab `storage`). */
export function useHandTuning(): HandTuning {
  const { data } = useSystemSettings()
  const [draft, setDraft] = useState<Record<string, number>>(() => loadSettingsDraft())

  useEffect(() => {
    const reload = () => setDraft(loadSettingsDraft())
    window.addEventListener(SETTINGS_DRAFT_EVENT, reload)
    window.addEventListener('storage', reload)
    return () => {
      window.removeEventListener(SETTINGS_DRAFT_EVENT, reload)
      window.removeEventListener('storage', reload)
    }
  }, [])

  return useMemo(() => resolveHandTuning(data?.settings, draft), [data, draft])
}
