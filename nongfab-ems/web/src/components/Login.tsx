import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../lib/auth'
import { LoginWelcome } from './LoginWelcome'
import { OrgLogos } from './OrgLogos'

export function Login() {
  const { login, autoLogoutReason } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
    } catch {
      setError('Incorrect username or password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-screen">
      <LoginWelcome />
      <OrgLogos variant="login" />
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>PTT LNG Terminal 2 Nong Fab Solar Forecasting</h1>
        <p className="login-subtitle">Sign in to continue</p>
        {autoLogoutReason && (
          <p role="status" className="login-notice">
            {autoLogoutReason}
          </p>
        )}
        <label htmlFor="username">Username</label>
        <input
          id="username"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {error && (
          <p role="alert" className="login-error">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
