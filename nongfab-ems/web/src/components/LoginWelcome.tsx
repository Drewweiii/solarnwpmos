import { useState } from 'react'
import { MascotFace } from './MascotFace'
import './LoginWelcome.css'

// This popup hands out the public *viewer* login (pttlng/12345) in the same
// breath, so the tour must only list what a viewer actually sees - exactly the
// 3 tabs a viewer gets: Forecast, 3D View, Energy Report. Simulation and
// Financial are operator/admin-only (Layout.tsx/App.tsx's RequireOperator,
// 2026-07-18) and were removed from here for exactly that reason. The old
// standalone "Irradiance Map" tab is gone too (2026-07-18 - merged into 3D
// View, App.tsx redirects /irradiance-map -> /3d), so it's folded into the 3D
// line rather than listed as its own feature.
const FEATURES = [
  'Forecast — กราฟพยากรณ์การผลิตไฟ เทียบกับของจริง',
  '3D View — โรงงานจำลอง 3 มิติ พร้อมเงา เส้นทางดวงอาทิตย์ และแผนที่ความเข้มแสง',
  'Energy Report — รายงานสรุปพลังงานรายวัน/รายเดือน/รายปี พร้อมค่าไฟที่ประหยัดและคาร์บอน',
]

/** A big popup on the login screen - "น้อง Solar" greets a first-time (or
 * just-signed-out) visitor, gives a quick tour of what the site does, and
 * hands out the public viewer login (pttlng/12345) so someone without an
 * operator/admin account can still get in. Shows every time this component
 * mounts (i.e. every time someone lands back on the login screen) rather
 * than persisting a "seen it" flag - it's short enough not to be annoying,
 * and doubles as a standing reminder of the viewer credentials.
 */
export function LoginWelcome() {
  const [isOpen, setIsOpen] = useState(true)
  if (!isOpen) return null

  return (
    <div className="login-welcome-backdrop" onClick={() => setIsOpen(false)}>
      <div
        className="login-welcome-card"
        role="dialog"
        aria-label="แนะนำเว็บไซต์โดยน้อง Solar"
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="login-welcome-close" onClick={() => setIsOpen(false)} aria-label="ปิดหน้าต่างแนะนำ">
          ×
        </button>

        <div className="login-welcome-mascot">
          <MascotFace mood="happy" />
        </div>

        <h2 className="login-welcome-title">สวัสดีครับ! ผมชื่อ "น้อง Solar" 👋</h2>
        <p className="login-welcome-text">
          ผมเป็นผู้ช่วย AI ประจำเว็บนี้ครับ เว็บนี้ใช้ติดตามและพยากรณ์การผลิตไฟฟ้าจากโซลาร์เซลล์ มีฟีเจอร์หลักๆ ดังนี้ครับ:
        </p>
        <ul className="login-welcome-features">
          {FEATURES.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
        <p className="login-welcome-text">แถมยังมีระบบแชทคุยกับผู้ชมคนอื่น และส่งข้อความถึงแอดมินได้อีกด้วยครับ</p>

        <p className="login-welcome-credentials">
          ถ้าคุณเป็นผู้ชมทั่วไป (ไม่ใช่ operator หรือ admin) ใช้ <strong>username: pttlng</strong> และ <strong>password: 12345</strong>{' '}
          เข้าระบบได้เลยครับ!
        </p>

        <button type="button" className="login-welcome-cta" onClick={() => setIsOpen(false)}>
          เข้าใจแล้ว เริ่มใช้งานเลย
        </button>
      </div>
    </div>
  )
}
