/** Per-browser chat identity for the visitor-network chat (VisitorNetwork.tsx
 * / useChatSocket.ts). The viewer/operator demo logins are shared
 * credentials (see api/src/nongfab_api/auth.py's DEMO_USERS) - multiple real
 * people can be signed in as the same `username` at once, so a display
 * name + avatar picked once per browser (LINE-style) is what actually tells
 * them apart in chat, not the account they logged in with.
 *
 * Nothing here is sent to any third party or costs anything - it's just
 * localStorage plus a small bundled emoji catalog.
 */

export interface AvatarOption {
  id: string
  emoji: string
  color: string
}

// A dozen options is enough variety without turning the picker into its own
// scrolling gallery - colors chosen to read clearly against both the light
// and dark theme (the circle itself carries the color, not surrounding UI).
export const AVATAR_OPTIONS: AvatarOption[] = [
  { id: 'dog', emoji: '🐶', color: '#F59E0B' },
  { id: 'cat', emoji: '🐱', color: '#F472B6' },
  { id: 'fox', emoji: '🦊', color: '#FB7185' },
  { id: 'panda', emoji: '🐼', color: '#64748B' },
  { id: 'koala', emoji: '🐨', color: '#94A3B8' },
  { id: 'lion', emoji: '🦁', color: '#FBBF24' },
  { id: 'penguin', emoji: '🐧', color: '#38BDF8' },
  { id: 'unicorn', emoji: '🦄', color: '#C084FC' },
  { id: 'frog', emoji: '🐸', color: '#4ADE80' },
  { id: 'octopus', emoji: '🐙', color: '#A78BFA' },
  { id: 'rocket', emoji: '🚀', color: '#60A5FA' },
  { id: 'star', emoji: '⭐', color: '#FACC15' },
]

// Reserved for the admin role - deliberately NOT in AVATAR_OPTIONS (never
// offered in the viewer/operator picker grid) since the user asked that
// admin skip picking anything and always just look like this.
export const ADMIN_AVATAR: AvatarOption = { id: 'crown', emoji: '👑', color: '#D4AF37' }
export const ADMIN_DISPLAY_NAME = 'admin'

const DEFAULT_AVATAR = AVATAR_OPTIONS[0]

export function avatarById(id: string | null | undefined): AvatarOption {
  if (id === ADMIN_AVATAR.id) return ADMIN_AVATAR
  return AVATAR_OPTIONS.find((a) => a.id === id) ?? DEFAULT_AVATAR
}

export interface ChatProfile {
  clientId: string
  displayName: string
  avatarId: string
}

const CLIENT_ID_KEY = 'nongfab_chat_client_id'
const PROFILE_KEY = 'nongfab_chat_profile'
const MAX_DISPLAY_NAME_LENGTH = 30

/** One random id per browser, generated once and reused forever after -
 * this (not `username`) is what useChatSocket.ts compares against to
 * decide "is this message mine" for bubble styling, since two different
 * people can share the same `username` under the shared demo logins.
 */
export function getOrCreateClientId(): string {
  let id = localStorage.getItem(CLIENT_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(CLIENT_ID_KEY, id)
  }
  return id
}

export function loadChatProfile(): ChatProfile | null {
  const raw = localStorage.getItem(PROFILE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as { displayName?: string; avatarId?: string }
    if (!parsed.displayName || !parsed.avatarId) return null
    return { clientId: getOrCreateClientId(), displayName: parsed.displayName, avatarId: parsed.avatarId }
  } catch {
    return null
  }
}

export function saveChatProfile(displayName: string, avatarId: string): ChatProfile {
  const trimmed = displayName.trim().slice(0, MAX_DISPLAY_NAME_LENGTH)
  localStorage.setItem(PROFILE_KEY, JSON.stringify({ displayName: trimmed, avatarId }))
  return { clientId: getOrCreateClientId(), displayName: trimmed, avatarId }
}

/** admin never goes through the picker - see the module docstring. */
export function adminProfile(): ChatProfile {
  return { clientId: getOrCreateClientId(), displayName: ADMIN_DISPLAY_NAME, avatarId: ADMIN_AVATAR.id }
}
