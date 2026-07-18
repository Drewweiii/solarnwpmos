import { useFeedbackInbox } from '../lib/queries'
import './AdminFeedbackPage.css'

const dateFormatter = new Intl.DateTimeFormat('th-TH', {
  timeZone: 'Asia/Bangkok',
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** Admin-only inbox for routes_feedback.py's `GET /feedback` - lists every
 * message visitors have sent via the VisitorNetwork widget's "ติดต่อแอดมิน"
 * tab, newest first. No reply/resolve workflow, matching the backend's own
 * intentionally minimal scope.
 */
export function AdminFeedbackPage() {
  const { data, isLoading, isError } = useFeedbackInbox()

  return (
    <div className="admin-feedback-page">
      <h2>ข้อความจากผู้ชม</h2>
      {isLoading && <p className="forecast-status">กำลังโหลด...</p>}
      {isError && <p className="forecast-status forecast-status-warn">โหลดข้อความไม่สำเร็จ</p>}
      {data && data.length === 0 && <p className="forecast-status">ยังไม่มีข้อความ</p>}
      {data && data.length > 0 && (
        <ul className="admin-feedback-list">
          {data.map((item) => (
            <li key={item.id} className="admin-feedback-item">
              <div className="admin-feedback-item-header">
                <span className="admin-feedback-item-author">
                  {item.username} <span className="admin-feedback-item-role">({item.role})</span>
                </span>
                <span className="admin-feedback-item-time">{dateFormatter.format(new Date(item.created_at))}</span>
              </div>
              <p className="admin-feedback-item-text">{item.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
