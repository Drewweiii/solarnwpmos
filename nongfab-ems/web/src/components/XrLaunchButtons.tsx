import { useEffect, useState } from 'react'
import { arAvailability } from '../lib/iosAr'
import { isXrModeSupported, scaleRatioLabel, xrStore } from '../lib/xr'
import { IosArLink } from './IosArLink'

/** Enter AR / VR, but only where the device can (2026-07-26, project M).
 *
 * Support is probed per mode and each button only appears once ITS OWN mode has
 * answered yes - `navigator.xr.isSessionSupported('immersive-ar')` and
 * `'immersive-vr'` are genuinely different answers on the same device (a
 * desktop headset does VR and not AR; a phone the reverse).
 *
 * On a device with no WebXR at all - which includes every iPhone and iPad,
 * because Safari does not implement it - this used to render nothing. As of
 * 2026-07-26 (project T) iOS instead gets an **AR Quick Look** link, Apple's
 * own AR mechanism, pointing at a USDZ built from the same surveyed geometry.
 * Same feature, entirely different plumbing; see `lib/iosAr.ts`.
 *
 * A device with neither still renders nothing, which remains the right answer:
 * a button that does nothing is worse than no button.
 *
 * The scale note is not decoration. The array spans hundreds of metres and AR
 * puts it on a table, so an unlabelled model invites reading its size as the
 * real one - the same overclaim as any unlabelled number elsewhere on this site.
 */
export function XrLaunchButtons({ sceneSpan, zone }: { sceneSpan: number; zone: string }) {
  const [arReady, setArReady] = useState(false)
  const [vrReady, setVrReady] = useState(false)
  // Evaluated once on mount rather than at module load: `relList.supports`
  // touches the DOM, and this module is imported by tests that render nothing.
  const [quickLook, setQuickLook] = useState(false)

  useEffect(() => setQuickLook(arAvailability() === 'quick-look'), [])

  useEffect(() => {
    let alive = true
    void isXrModeSupported('immersive-ar').then((ok) => alive && setArReady(ok))
    void isXrModeSupported('immersive-vr').then((ok) => alive && setVrReady(ok))
    // The probes are promises; a viewer who navigates away mid-probe must not
    // get a setState on an unmounted component.
    return () => {
      alive = false
    }
  }, [])

  // iOS: no WebXR, but Quick Look is the real thing rather than a fallback.
  if (quickLook && !arReady) return <IosArLink zone={zone} sceneSpan={sceneSpan} />

  if (!arReady && !vrReady) return null

  return (
    <div className="xr-launch">
      {arReady && (
        <button type="button" className="xr-launch-button" onClick={() => xrStore.enterAR()}>
          📱 ดูแบบ AR
        </button>
      )}
      {vrReady && (
        <button type="button" className="xr-launch-button" onClick={() => xrStore.enterVR()}>
          🥽 ดูแบบ VR
        </button>
      )}
      <span className="xr-launch-note">
        AR ย่อทั้งไซต์ลงเป็นแบบจำลองตั้งโต๊ะ มาตราส่วนราว {scaleRatioLabel(sceneSpan)} — ขนาดที่เห็นไม่ใช่ขนาดจริง
      </span>
    </div>
  )
}
