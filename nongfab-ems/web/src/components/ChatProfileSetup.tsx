import { useState } from 'react'
import { avatarById, AVATAR_OPTIONS, saveChatProfile, type ChatProfile } from '../lib/chatProfile'
import { MascotFace } from './MascotFace'
import './ChatProfileSetup.css'

/** The name/avatar picker for the site-wide visitor chat (see chatProfile.ts's
 * module docstring for why this exists at all - shared demo logins can't
 * tell two different real people apart by username). Shared by two call
 * sites: `ChatProfileGate` (Layout.tsx - the very first time, right after
 * login, before the dashboard is reachable at all - per the user's explicit
 * 2026-07-18 request to move this earlier instead of leaving it undiscovered
 * inside the chat panel) and `VisitorNetwork.tsx` (the "✏️ edit profile"
 * flow later, and as a defense-in-depth fallback if a profile somehow isn't
 * present by the time someone opens the chat panel - e.g. localStorage
 * cleared mid-session).
 */
export function ChatProfileSetup({
  initial,
  onSaved,
  onCancel,
}: {
  initial: ChatProfile | null
  onSaved: (profile: ChatProfile) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState(initial?.displayName ?? '')
  const [avatarId, setAvatarId] = useState(initial?.avatarId ?? AVATAR_OPTIONS[0].id)
  // The mascot introduces itself first - only swap the preview over to
  // showing the visitor's own chosen avatar once they've actually picked
  // one (or immediately when editing an existing profile, since there's
  // already a real choice to show). Per the user's explicit request
  // (2026-07-18): picking an avatar should visibly show that avatar in
  // place of น้อง Solar, not leave the mascot showing regardless of choice.
  const [hasPickedAvatar, setHasPickedAvatar] = useState(initial != null)
  const selectedAvatar = avatarById(avatarId)

  return (
    <form
      className="chat-profile-setup"
      onSubmit={(e) => {
        e.preventDefault()
        if (!name.trim()) return
        onSaved(saveChatProfile(name, avatarId))
      }}
    >
      <div className="chat-profile-setup-mascot" aria-hidden="true">
        {hasPickedAvatar ? (
          <span className="chat-profile-setup-avatar-preview" style={{ background: selectedAvatar.color }}>
            {selectedAvatar.emoji}
          </span>
        ) : (
          <MascotFace mood="idle" />
        )}
      </div>
      <p className="chat-profile-setup-note">
        {initial
          ? 'น้อง Solar: แก้ไขชื่อและ avatar ที่จะแสดงในแชทได้เลยครับ'
          : 'น้อง Solar: ตั้งชื่อและเลือก avatar ที่จะแสดงในแชท (เหมือน LINE) ก่อนเริ่มคุยกันได้เลยครับ'}
      </p>
      <label className="chat-profile-setup-name-label" htmlFor="chat-profile-setup-name">
        ชื่อที่แสดง
      </label>
      <input
        id="chat-profile-setup-name"
        type="text"
        className="chat-profile-setup-input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="ชื่อของคุณ"
        maxLength={30}
      />
      <div className="chat-profile-setup-avatar-grid" role="radiogroup" aria-label="เลือก avatar">
        {AVATAR_OPTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="radio"
            aria-checked={avatarId === a.id}
            aria-label={`avatar ${a.id}`}
            className={avatarId === a.id ? 'chat-profile-setup-avatar-option selected' : 'chat-profile-setup-avatar-option'}
            style={{ background: a.color }}
            onClick={() => {
              setAvatarId(a.id)
              setHasPickedAvatar(true)
            }}
          >
            {a.emoji}
          </button>
        ))}
      </div>
      <button type="submit" className="chat-profile-setup-submit" disabled={!name.trim()}>
        {initial ? 'บันทึก' : 'เริ่มแชท'}
      </button>
      {onCancel && (
        <button type="button" className="chat-profile-setup-cancel" onClick={onCancel}>
          ยกเลิก
        </button>
      )}
    </form>
  )
}
