import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { loadChatProfile, type ChatProfile } from '../lib/chatProfile'
import { useAuth } from '../lib/auth'
import { useDeployWatch } from '../lib/deployWatch'
import { AIAssistant } from './AIAssistant'
import { ChatProfileSetup } from './ChatProfileSetup'
import { OrgLogos } from './OrgLogos'
import { SiteCredit } from './SiteCredit'
import { VisitorNetwork } from './VisitorNetwork'

export function Layout() {
  const { username, role, logout, forceLogout } = useAuth()
  // Auto-logout whenever a new deploy goes live (backend on Railway or
  // frontend on Cloudflare) - see deployWatch.ts's own docstring for why.
  useDeployWatch(() => forceLogout('เว็บไซต์มีการอัปเดตใหม่ กรุณาเข้าสู่ระบบอีกครั้ง'))

  // Per the user's explicit request (2026-07-18): set up the chat name/
  // avatar right after login, before the dashboard is reachable at all -
  // it used to only surface once someone happened to open the chat panel,
  // which most visitors never did. This blocks the whole authenticated app
  // (not just the chat widget) the very first time only; VisitorNetwork.tsx
  // still has its own fallback for the (rare) case a profile disappears
  // mid-session, e.g. localStorage cleared without logging out.
  const [chatProfile, setChatProfile] = useState<ChatProfile | null>(() => loadChatProfile())

  if (!chatProfile) {
    return (
      <div className="chat-profile-gate-screen">
        <div className="chat-profile-gate-card">
          <h1 className="chat-profile-gate-title">ก่อนเข้าเว็บ...</h1>
          <ChatProfileSetup initial={null} onSaved={setChatProfile} />
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-brand">Nong Fab Solar EMS</div>
        <nav className="app-nav">
          <NavLink to="/forecast" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Forecast
          </NavLink>
          <NavLink to="/simulation" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Simulation
          </NavLink>
          <NavLink to="/financial" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Financial
          </NavLink>
          <NavLink to="/3d" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            3D View
          </NavLink>
          <NavLink to="/energy-report" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Energy Report
          </NavLink>
          <NavLink to="/irradiance-map" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Irradiance Map
          </NavLink>
          {role === 'admin' ? (
            <NavLink to="/admin/feedback" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              Feedback
            </NavLink>
          ) : (
            // Non-admins never see who submitted feedback (server-side
            // require_role("admin") on GET /feedback enforces this too) -
            // this slot instead shows a website-author credit strip, left
            // blank until the user supplies real credit text.
            <SiteCredit />
          )}
        </nav>
        <div className="app-header-user">
          <span>
            {username} <span className="app-header-role">({role})</span>
          </span>
          <button type="button" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        <OrgLogos variant="footer" />
      </footer>
      <AIAssistant />
      <VisitorNetwork />
    </div>
  )
}
