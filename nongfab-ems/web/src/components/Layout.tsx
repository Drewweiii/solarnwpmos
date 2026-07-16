import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function Layout() {
  const { username, role, logout } = useAuth()

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
    </div>
  )
}
