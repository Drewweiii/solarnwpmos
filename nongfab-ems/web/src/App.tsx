import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'
import './App.css'
import { Layout } from './components/Layout'
import { Login } from './components/Login'
import { AuthProvider, useAuth } from './lib/auth'
import { ForecastPage } from './pages/ForecastPage'

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
