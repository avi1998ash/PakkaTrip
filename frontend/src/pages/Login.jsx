import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Brand } from '../components/ui'
import { homeFor, isPortalUser, useAuth } from '../lib/auth'

const DEMO = {
  admin: ['admin@pakkatrip.com', 'admin123'],
  operator: ['himalayan@pakkatrip.com', 'operator123'],
}

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (isPortalUser(user)) return <Navigate to={homeFor(user)} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const u = await login(email, password)
      navigate(homeFor(u), { replace: true })
    } catch (err) {
      setError(err.status === 401 ? 'Invalid credentials' : err.message)
    } finally { setBusy(false) }
  }
  const fill = who => { setEmail(DEMO[who][0]); setPassword(DEMO[who][1]); setError('') }

  return (
    <section className="min-h-screen grid place-items-center px-4 py-6"
      style={{ background: 'radial-gradient(1200px 500px at 100% 0%, rgb(242 140 40 / .18), transparent 60%), linear-gradient(160deg, #0B2E59 0%, #0E3A70 100%)' }}>
      <div className="w-full max-w-[410px] bg-white rounded-2xl px-7 py-8 shadow-[0_20px_60px_rgba(0,0,0,.25)]">
        <Brand />
        <h1 className="text-[22px] font-semibold mt-4">Sign in</h1>
        <p className="text-muted mt-1 mb-5">Manage your trips and bookings</p>
        <form onSubmit={submit} noValidate>
          <div className="mb-3.5"><label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></div>
          <div className="mb-3.5"><label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
          {error && <div className="text-danger bg-danger-soft rounded-lg px-3 py-2 text-[13px] font-medium mb-3" role="alert">{error}</div>}
          <button className="btn btn-primary w-full justify-center py-[11px]" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <div className="mt-[18px] p-3 bg-saffron-soft rounded-[10px] text-[12.5px] text-[#7A4510]">
          <div className="font-bold mb-1.5">Demo logins</div>
          {[['Admin', 'admin'], ['Operator', 'operator']].map(([label, key]) => (
            <div key={key} className="flex items-center gap-2 py-1">
              <span className="font-bold min-w-16">{label}</span>
              <span className="flex-1 min-w-0 break-all">{DEMO[key][0]} / {DEMO[key][1]}</span>
              <button className="link" type="button" onClick={() => fill(key)}>Fill in</button>
            </div>
          ))}
        </div>
        <p className="text-center mt-4 text-[13px]"><a className="link" href="/">← Back to PakkaTrip for travellers</a></p>
      </div>
    </section>
  )
}
