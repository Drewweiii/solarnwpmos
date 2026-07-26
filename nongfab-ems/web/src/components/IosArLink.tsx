import { zoneUsdzUrl } from '../lib/api'
import { useAuth } from '../lib/auth'
import { usdzScaleRatioLabel } from '../lib/iosAr'

/** The AR Quick Look link for iPhone and iPad (2026-07-26, project T).
 *
 * THE ANCHOR'S SHAPE IS LOAD-BEARING, NOT STYLING. Apple requires `<a rel="ar">`
 * to contain exactly **one** child element, an `<img>` or `<picture>`. With any
 * other content - a `<span>`, two children, a bare text node - Safari stops
 * treating it as an AR link and simply navigates to the .usdz, which downloads
 * a file the viewer cannot open. That failure looks exactly like "AR is broken
 * on iPhone", so the label here is drawn *into* the image rather than placed
 * beside it, and the caption sits outside the anchor entirely.
 *
 * The image is an inline SVG data URI: no network request, no extra asset to
 * deploy, and it renders identically in both themes.
 */

const LABEL_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="260" height="46">
<rect width="260" height="46" rx="10" fill="#0b1220"/>
<text x="130" y="29" text-anchor="middle" fill="#f5f3ff"
 font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="15" font-weight="600">
📱 ดูแบบ AR บน iPhone / iPad</text></svg>`

const LABEL_SRC = `data:image/svg+xml;utf8,${encodeURIComponent(LABEL_SVG)}`

export function IosArLink({ zone, sceneSpan }: { zone: string; sceneSpan: number }) {
  const { token } = useAuth()
  if (!token) return null

  return (
    <div className="ios-ar">
      {/* Exactly one child element. Do not add a sibling here. */}
      <a rel="ar" href={zoneUsdzUrl(zone, token)} className="ios-ar-link">
        <img src={LABEL_SRC} alt="ดูแบบ AR บน iPhone หรือ iPad" width={260} height={46} />
      </a>
      <span className="ios-ar-note">
        เปิดด้วย AR Quick Look ของ iOS · ย่อทั้งไซต์ลงเป็นแบบจำลองตั้งโต๊ะ มาตราส่วนราว{' '}
        {usdzScaleRatioLabel(sceneSpan)} — ขนาดที่เห็นไม่ใช่ขนาดจริง
      </span>
    </div>
  )
}
