import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'
import './App.css'
import { Layout } from './components/Layout'
import { Login } from './components/Login'
import { AuthProvider, useAuth } from './lib/auth'
import { FinancialPage } from './pages/FinancialPage'
import { ForecastPage } from './pages/ForecastPage'
import { SimulationPlaygroundPage } from './pages/SimulationPlaygroundPage'

// Code-split the heavy per-page dependencies (Three.js, MapLibre) into
// separate chunks fetched on navigation, not bundled into the initial
// login/forecast load - ForecastPage (Recharts) stays eager since it's the
// default landing page and needed immediately after login anyway. See
// web/README.md "Known gaps" - this was deferred until Feature D/E (the
// MapLibre page) landed, since one pass across every heavy per-page
// dependency makes more sense than splitting incrementally.
const Solar3DPage = lazy(() => import('./pages/Solar3DPage').then((m) => ({ default: m.Solar3DPage })))
const EnergyReportPage = lazy(() => import('./pages/EnergyReportPage').then((m) => ({ default: m.EnergyReportPage })))
const IrradianceMapPage = lazy(() => import('./pages/IrradianceMapPage').then((m) => ({ default: m.IrradianceMapPage })))
const AdminFeedbackPage = lazy(() => import('./pages/AdminFeedbackPage').then((m) => ({ default: m.AdminFeedbackPage })))

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
})

function RequireAdmin({ children }: { children: ReactNode }) {
  const { role } = useAuth()
  if (role !== 'admin') return <Navigate to="/forecast" replace />
  return <>{children}</>
}

// Simulation and Financial are operator-and-up (mirrors the backend's own
// require_role("operator") on POST /simulate/{zone} and POST /financial -
// see routes_simulate.py/routes_financial.py, already the real access
// control; this just keeps a viewer from landing on a page whose only
// actions already 403 for them - per the user's own 2026-07-18 request to
// hide these two from viewer entirely, not just gate the button). Exported
// so it's directly testable without going through the full app shell.
export function RequireOperator({ children }: { children: ReactNode }) {
  const { role } = useAuth()
  if (role === 'viewer') return <Navigate to="/forecast" replace />
  return <>{children}</>
}

function RequireAuth() {
  const { token } = useAuth()
  if (!token) return <Login />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/forecast" replace />} />
        <Route path="/forecast" element={<ForecastPage />} />
        <Route
          path="/simulation"
          element={
            <RequireOperator>
              <SimulationPlaygroundPage />
            </RequireOperator>
          }
        />
        <Route
          path="/financial"
          element={
            <RequireOperator>
              <FinancialPage />
            </RequireOperator>
          }
        />
        <Route
          path="/admin/feedback"
          element={
            <RequireAdmin>
              <Suspense fallback={<p className="forecast-status">Loading…</p>}>
                <AdminFeedbackPage />
              </Suspense>
            </RequireAdmin>
          }
        />
        <Route
          path="/3d"
          element={
            <Suspense fallback={<p className="forecast-status">Loading…</p>}>
              <Solar3DPage />
            </Suspense>
          }
        />
        <Route
          path="/energy-report"
          element={
            <Suspense fallback={<p className="forecast-status">Loading…</p>}>
              <EnergyReportPage />
            </Suspense>
          }
        />
        <Route
          path="/irradiance-map"
          element={
            <Suspense fallback={<p className="forecast-status">Loading…</p>}>
              <IrradianceMapPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/forecast" replace />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <RequireAuth />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

export default App
