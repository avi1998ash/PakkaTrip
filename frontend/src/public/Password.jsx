import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

/** Where each kind of account logs in after a reset. */
const loginFor = role => role === 'traveller' ? '/account' : '/partner/login'

/** "Forgot password?" — for travellers and partner (operator/admin) accounts alike. */
export function ForgotPassword() {
  const [params] = useSearchParams()
  const partner = params.get('for') === 'partner'
  const [email, setEmail] = useState(params.get('email') || '')
  const [sent, setSent] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { document.title = 'Forgot password — PakkaTrip' }, [])

  async function submit(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    setBusy(true); setError('')
    try { setSent(await api('/public/auth/password/forgot/', { method: 'POST', body: { email } })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const back = <Link className="link" to={partner ? '/partner/login' : '/account'}>← Back to {partner ? 'partner ' : ''}login</Link>

  return (
    <div className="container"><div className="card auth-wrap">
      {sent ? (
        <div className="auth-body">
          <h3 style={{ margin: 0 }}>Check your email</h3>
          <p style={{ margin: 0 }}>{sent.detail}</p>
          <p className="help" style={{ margin: 0 }}>The link works once and expires in 1 hour. No email? Wait a minute, check spam, then try again.</p>
          {sent.dev_link && <div className="demo-hint"><span><b>Development:</b> email isn't set up, so here's the link.</span>
            <a className="link" href={sent.dev_link}>Open reset link</a></div>}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{back}
            <button type="button" className="link" onClick={() => setSent(null)}>Use a different email</button></div>
        </div>
      ) : (
        <form className="auth-body" onSubmit={submit} noValidate>
          <h3 style={{ margin: 0 }}>Forgot your password?</h3>
          <p className="help" style={{ margin: 0 }}>Enter the email you log in with. We'll send you a link to set a new password.</p>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div><label htmlFor="fp-email">Email</label>
            <input id="fp-email" type="email" required autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></div>
          <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button>
          <p style={{ textAlign: 'center', margin: 0 }}>{back}</p>
        </form>
      )}
    </div></div>
  )
}

/** The page the emailed link opens: /reset-password?uid=…&token=… */
export function ResetPassword() {
  const [params] = useSearchParams()
  const uid = params.get('uid'), token = params.get('token')
  const [f, setF] = useState({ password: '', confirm: '' })
  const [done, setDone] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { document.title = 'Set a new password — PakkaTrip' }, [])

  if (!uid || !token) return (
    <div className="container"><div className="card auth-wrap empty-state"><h3>This reset link is incomplete</h3>
      <p>Open the link from the email again, or ask for a new one.</p>
      <Link className="btn btn-primary" to="/forgot-password">Get a new link</Link></div></div>
  )

  async function submit(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    if (f.password !== f.confirm) { setError("The two passwords don't match."); return }
    setBusy(true); setError('')
    try { setDone(await api('/public/auth/password/reset/', { method: 'POST', body: { uid, token, password: f.password } })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  if (done) return (
    <div className="container"><div className="card auth-wrap empty-state"><h3>Password changed</h3>
      <p>You can now log in to <b>{done.email}</b> with your new password.</p>
      <Link className="btn btn-primary" to={loginFor(done.role)}>{done.role === 'traveller' ? 'Log in' : 'Go to partner login'}</Link></div></div>
  )

  const expired = /invalid or has expired/.test(error)
  return (
    <div className="container"><div className="card auth-wrap">
      <form className="auth-body" onSubmit={submit} noValidate>
        <h3 style={{ margin: 0 }}>Set a new password</h3>
        {error && <div className="form-error" role="alert">{error}{expired && <> <Link className="link" to="/forgot-password">Get a new link</Link></>}</div>}
        <div><label htmlFor="rp-new">New password</label>
          <input id="rp-new" type="password" required minLength={6} maxLength={64} autoComplete="new-password" value={f.password}
            onChange={e => setF(s => ({ ...s, password: e.target.value }))} />
          <div className="help">At least 6 characters (8 for operator and admin accounts).</div></div>
        <div><label htmlFor="rp-confirm">Confirm new password</label>
          <input id="rp-confirm" type="password" required minLength={6} maxLength={64} autoComplete="new-password" value={f.confirm}
            onChange={e => setF(s => ({ ...s, confirm: e.target.value }))} /></div>
        <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save new password'}</button>
      </form>
    </div></div>
  )
}
