import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useFeedback } from '../components/feedback'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { firstName } from './shared'

const DEMO = ['priya@example.com', 'travel123']

/** Traveller login / signup (portal staff use /partner/login). */
export default function Account() {
  const [params] = useSearchParams()
  const next = params.get('next') || '/my-bookings'
  const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/my-bookings'   // only same-site redirects
  const { user, adopt, logout } = useAuth()
  const { toast } = useFeedback()
  const navigate = useNavigate()
  const [tab, setTab] = useState('login')
  const [f, setF] = useState({ name: '', phone: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  if (user?.role === 'traveller') return (
    <div className="container"><div className="card auth-wrap empty-state"><h3>You're logged in as {user.name}</h3>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}><Link className="btn btn-primary" to={safeNext}>Continue</Link>
        <button className="btn" onClick={() => { logout(); toast('Logged out') }}>Log out</button></div></div></div>
  )

  async function submit(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    setBusy(true); setError('')
    try {
      const d = tab === 'signup'
        ? await api('/public/auth/signup/', { method: 'POST', body: f })
        : await api('/public/auth/login/', { method: 'POST', body: { email: f.email, password: f.password } })
      const u = adopt(d)
      toast(tab === 'signup' ? `Welcome to PakkaTrip, ${firstName(u.name)}!` : `Welcome back, ${firstName(u.name)}!`)
      navigate(safeNext, { replace: true })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="container"><div className="card auth-wrap">
      {user && <div className="form-error" style={{ margin: 16 }}>You're signed in to the partner portal. Logging in here as a traveller will sign you out of it.</div>}
      <div className="auth-tabs" role="tablist">
        <button className={tab === 'login' ? 'active' : ''} onClick={() => { setTab('login'); setError('') }}>Log in</button>
        <button className={tab === 'signup' ? 'active' : ''} onClick={() => { setTab('signup'); setError('') }}>Sign up</button>
      </div>
      <form className="auth-body" onSubmit={submit} noValidate key={tab}>
        {error && <div className="form-error" role="alert">{error}</div>}
        {tab === 'signup' && <>
          <div><label>Full name</label><input type="text" required maxLength={50} autoComplete="name" value={f.name} onChange={e => set('name', e.target.value)} /></div>
          <div><label>Mobile number</label><input type="tel" required pattern="[6-9][0-9]{9}" maxLength={10} inputMode="numeric" autoComplete="tel-national" value={f.phone} onChange={e => set('phone', e.target.value)} /></div>
        </>}
        <div><label>Email</label><input type="email" required autoComplete="username" value={f.email} onChange={e => set('email', e.target.value)} /></div>
        <div><label>Password</label><input type="password" required minLength={6} autoComplete={tab === 'signup' ? 'new-password' : 'current-password'} value={f.password} onChange={e => set('password', e.target.value)} />
          {tab === 'signup' && <div className="help">At least 6 characters.</div>}</div>
        <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={busy}>{busy ? 'Please wait…' : tab === 'signup' ? 'Create account' : 'Log in'}</button>
        {tab === 'login' && <div className="demo-hint"><span><b>Demo traveller:</b> {DEMO[0]} / {DEMO[1]}</span>
          <button type="button" className="link" onClick={() => setF(s => ({ ...s, email: DEMO[0], password: DEMO[1] }))}>Fill in</button></div>}
        <div className="or">or</div>
        <button type="button" className="btn btn-block" onClick={() => { toast('Continuing as guest'); navigate(safeNext === '/my-bookings' ? '/search' : safeNext) }}>Continue as guest</button>
        <p className="help" style={{ textAlign: 'center', margin: 0 }}>Guests can book and pay; tickets stay on this device. Operator or admin? <a href="/partner/login">Partner login →</a></p>
      </form>
    </div></div>
  )
}
