import { useEffect, useState } from 'react'
import { isXrModeSupported, scaleRatioLabel, xrStore } from '../lib/xr'

/** Enter AR / VR, but only where the device can (2026-07-26, project M).
 *
 * Support is probed per mode and each button only appears once ITS OWN mode has
 * answered yes - `navigator.xr.isSessionSupported('immersive-ar')` and
 * `'immersive-vr'` are genuinely different answers on the same device (a
 * desktop headset does VR and not AR; a phone the reverse).
 *
 * Nothing renders on a device with no WebXR at all, which includes every
 * iPhone and iPad - Safari does not implement it. A button that does nothing on
 * the device half the audience is holding would be worse than no button.
 *
 * The scale note is not decoration. The array spans hundreds of metres and AR
 * puts it on a table, so an unlabelled model invites reading its size as the
 * real one - the same overclaim as any unlabelled number elsewhere on this site.
 */
export function XrLaunchButtons({ sceneSpan }: { sceneSpan: number }) {
  const [arReady, setArReady] = useState(false)
  const [vrReady, setVrReady] = useState(false)

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
