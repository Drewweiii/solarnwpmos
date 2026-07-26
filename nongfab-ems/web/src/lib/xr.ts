/** Putting the plant on a table, or standing in it (2026-07-26, project M).
 *
 * The 3D view is already a react-three-fiber scene built from the array's real
 * surveyed geometry, so WebXR needs no new scene - only a session to render the
 * existing one into. Two modes: AR drops Nong Fab onto whatever surface the
 * phone is pointed at, VR puts the viewer inside the array.
 *
 * SUPPORT IS NARROW AND THE UI HAS TO ADMIT IT. Android Chrome and headset
 * browsers support WebXR AR; **iPhone and iPad Safari do not support WebXR at
 * all**. A button that does nothing on the device half the audience is holding
 * is worse than no button, so support is probed per mode and each button only
 * appears once its own mode has answered yes.
 */

import { createXRStore } from '@react-three/xr'

/** One store for the app. The scene mounts once and both modes share it.
 *
 * `emulate: false` matters. By default the library injects a WebXR emulator
 * whenever it does not find a real device, and that injection reaches for
 * `WebGL2RenderingContext` - which does not exist under jsdom, so importing
 * this module threw an unhandled rejection into every test that touched it.
 * The emulator is a development convenience this project has no use for
 * (the real check is a real Android phone or headset), and it is not worth
 * an unhandled rejection in the test run to keep.
 */
export const xrStore = createXRStore({ emulate: false })

export type XrMode = 'immersive-ar' | 'immersive-vr'

/** Whether this browser/device can actually enter `mode`.
 *
 * Always false rather than throwing where `navigator.xr` is absent entirely
 * (every desktop browser without a headset, and all of iOS) - the caller's
 * correct response is to render nothing, and an exception would make that
 * harder rather than clearer.
 */
export async function isXrModeSupported(mode: XrMode): Promise<boolean> {
  const nav = navigator as Navigator & {
    xr?: { isSessionSupported?: (mode: string) => Promise<boolean> }
  }
  if (!nav.xr?.isSessionSupported) return false
  try {
    return await nav.xr.isSessionSupported(mode)
  } catch {
    // Some browsers reject rather than resolve false for an unknown mode.
    return false
  }
}

/** How far to shrink the scene so the site fits on a table in AR.
 *
 * The scene is modelled in metres and the array spans hundreds of them, so at
 * 1:1 an AR visitor stands inside a structure larger than the room. This maps
 * the visible span onto a tabletop-sized object.
 *
 * The scale is returned rather than hidden so the UI can print it: an AR view
 * with no stated scale invites reading the model's size as the real one, which
 * is the same overclaim as any unlabelled number on this site.
 */
export const TABLETOP_SPAN_M = 0.6

export function tabletopScale(sceneSpan: number): number {
  if (!Number.isFinite(sceneSpan) || sceneSpan <= 0) return 1
  return TABLETOP_SPAN_M / sceneSpan
}

/** "1 : 250" for the on-screen scale note. Rounded to something a person can
 * read, not to float precision. */
export function scaleRatioLabel(sceneSpan: number): string {
  const scale = tabletopScale(sceneSpan)
  if (scale >= 1) return '1 : 1'
  return `1 : ${Math.round(1 / scale)}`
}
