/** AR on iPhone and iPad, via AR Quick Look (2026-07-26, project T).
 *
 * Project M's WebXR buttons deliberately never appear on iOS, because Safari
 * does not implement WebXR - correct, and it left every iPhone and iPad in the
 * room with nothing. Apple's own mechanism is AR Quick Look: an `<a rel="ar">`
 * pointing at a `.usdz`, which Safari hands to the system AR viewer.
 *
 * There are three details that decide whether this works at all, and all three
 * are easy to get wrong silently - the link just navigates to a downloaded file
 * instead of opening AR, which looks like "AR is broken on iPhone".
 */

/** Whether the browser understands `rel="ar"`.
 *
 * This is Apple's documented feature test and it is preferred over sniffing the
 * user agent: it answers the question actually being asked ("will this link
 * open AR?") rather than a proxy for it, and it goes false automatically on any
 * future iOS that drops Quick Look or any browser that gains it.
 */
export function supportsArQuickLook(): boolean {
  if (typeof document === 'undefined') return false
  try {
    const anchor = document.createElement('a')
    return Boolean(anchor.relList?.supports?.('ar'))
  } catch {
    // `DOMTokenList.supports()` is specified to THROW a TypeError - not return
    // false - when the attribute has no supported-tokens definition at all,
    // which is the case for `rel` on anchors in every engine that does not
    // implement Quick Look. Unguarded, the feature test for AR would take down
    // the page on Firefox rather than quietly answering "no AR here". Caught
    // 2026-07-26 by this throwing under jsdom.
    return false
  }
}

/** Whether this is an Apple touch device.
 *
 * Used only to explain *why* AR is unavailable when the feature test fails, so
 * a viewer on a desktop and a viewer on an iPad running a browser without Quick
 * Look get different, accurate messages.
 *
 * The `MacIntel` clause is not paranoia: since iPadOS 13 an iPad reports itself
 * as a Mac in `navigator.platform`, and the only reliable way to tell it from a
 * real desktop is that a desktop has no touch points.
 */
export function isAppleTouchDevice(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  if (/iP(hone|od|ad)/.test(ua)) return true
  return navigator.platform === 'MacIntel' && (navigator.maxTouchPoints ?? 0) > 1
}

export type ArAvailability = 'quick-look' | 'apple-no-quick-look' | 'not-apple'

export function arAvailability(): ArAvailability {
  if (supportsArQuickLook()) return 'quick-look'
  return isAppleTouchDevice() ? 'apple-no-quick-look' : 'not-apple'
}

/** "1 : 250" for the scale note beside the AR link.
 *
 * Mirrors `xr.ts`'s function of the same purpose, and exists for the same
 * reason: an AR model with no stated scale invites reading its size as the real
 * one. The backend applies the scale inside the USDZ and reports it in an
 * `X-Model-Scale` header, but the link is followed by the system viewer rather
 * than by fetch, so the UI computes the same ratio from the same span constant.
 */
export const TABLETOP_SPAN_M = 0.6

export function usdzScaleRatioLabel(sceneSpan: number): string {
  if (!Number.isFinite(sceneSpan) || sceneSpan <= 0) return '1 : 1'
  const scale = TABLETOP_SPAN_M / sceneSpan
  if (scale >= 1) return '1 : 1'
  return `1 : ${Math.round(1 / scale)}`
}
