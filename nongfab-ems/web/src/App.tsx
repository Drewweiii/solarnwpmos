import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
})

function RequireAuth() {
  const { token } = useAuth()
  if (!token) return <Login />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/forecast" replace />} />
        <Route path="/forecast" element={<ForecastPage />} />
        <Route path="/simulation" element={<SimulationPlaygroundPage />} />
        <Route path="/financial" element={<FinancialPage />} />
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
