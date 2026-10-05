import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { Brand, Icon } from '../components/ui'
import { api } from '../lib/api'
import { homeFor, isPortalUser, useAuth } from '../lib/auth'
import { useApi } from '../lib/useApi'

/** Tour operators apply here, then they're signed straight in. The mobile number is confirmed by SMS code when
 *  that's switched on (Admin → Settings); otherwise PakkaTrip confirms it by calling. */
export default function Signup() {
  const { user, adopt } = useAuth()
  const { data: cfg } = useApi('/public/config/')
  const otpOn = !!cfg?.sms_otp_enabled
  const [f, setF] = useState({ business_name: '', owner_name: '', city: '', phone: '', email: '', password: '', otp: '' })
  const [sentTo, setSentTo] = useState('')
  const [devCode, setDevCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [signedUp, setSignedUp] = useState(false)
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  // A new operator goes straight to Verification to start adding their documents.
  if (isPortalUser(user)) return <Navigate to={signedUp && user.role === 'operator' ? '/operator/verification' : homeFor(user)} replace />

  async function sendCode() {
    if (!/^[6-9]\d{9}$/.test(f.phone)) { setError('Enter a 10-digit Indian mobile number first.'); return }
    setBusy('otp'); setError('')
    try {
      const d = await api('/public/partner/otp/', { method: 'POST', body: { phone: f.phone } })
      setSentTo(f.phone); setDevCode(d.dev_code || '')
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  async function submit(e) {
    e.preventDefault()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    if (otpOn && sentTo !== f.phone) { setError('Verify your mobile number: tap “Send code” and enter the code from the SMS.'); return }
    setBusy('signup'); setError('')
    try {
      const { otp, ...rest } = f
      const d = await api('/public/partner/signup/', { method: 'POST', body: otpOn ? f : rest })
      setSignedUp(true)
      adopt(d)
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  return (
    <section className="min-h-screen grid place-items-center px-4 py-6"
      style={{ background: 'radial-gradient(1200px 500px at 100% 0%, rgb(242 140 40 / .18), transparent 60%), linear-gradient(160deg, #0B2E59 0%, #0E3A70 100%)' }}>
      <div className="w-full max-w-[520px] bg-white rounded-2xl px-7 py-8 shadow-[0_20px_60px_rgba(0,0,0,.25)]">
        <Brand />
        <h1 className="text-[22px] font-semibold mt-4">List your trips on PakkaTrip</h1>
        <p className="text-muted mt-1 mb-5">Free to list, no commission. Set up your packages right away; they go live once we've verified your business.</p>
        <form onSubmit={submit} noValidate>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="form-grid">
            <div className="full"><label htmlFor="business_name">Business name</label>
              <input id="business_name" required minLength={3} maxLength={120} value={f.business_name} onChange={e => set('business_name', e.target.value)} /></div>
            <div><label htmlFor="owner_name">Owner's full name</label>
              <input id="owner_name" required maxLength={100} autoComplete="name" value={f.owner_name} onChange={e => set('owner_name', e.target.value)} /></div>
            <div><label htmlFor="city">City</label>
              <input id="city" required maxLength={60} value={f.city} onChange={e => set('city', e.target.value)} placeholder="Where you're based" /></div>
            <div className="full"><label htmlFor="phone">Mobile number</label>
              <div className="flex gap-2">
                <input id="phone" type="tel" required inputMode="numeric" pattern="[6-9][0-9]{9}" maxLength={10} title="10-digit Indian mobile number"
                  autoComplete="tel-national" value={f.phone} onChange={e => set('phone', e.target.value.replace(/\D/g, ''))} />
                {otpOn && <button className="btn flex-none" type="button" onClick={sendCode} disabled={busy === 'otp'}>
                  {busy === 'otp' ? 'Sending…' : sentTo && sentTo === f.phone ? 'Resend code' : 'Send code'}</button>}
              </div>
              {!otpOn && <div className="help">We'll call you on this number to confirm it before approving your business.</div>}
              {otpOn && sentTo && sentTo === f.phone && <div className="help" style={{ color: 'var(--color-leaf)' }}><Icon name="check" size={13} /> Code sent by SMS to {sentTo}.</div>}
              {devCode && <div className="help">Development mode (no SMS sent): your code is <b>{devCode}</b></div>}</div>
            {otpOn && sentTo && sentTo === f.phone && (
              <div className="full"><label htmlFor="otp">6-digit code from the SMS</label>
                <input id="otp" required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={f.otp}
                  onChange={e => set('otp', e.target.value.replace(/\D/g, ''))} /></div>
            )}
            <div className="full"><label htmlFor="email">Email (you'll sign in with this)</label>
              <input id="email" type="email" required autoComplete="username" value={f.email} onChange={e => set('email', e.target.value)} /></div>
            <div className="full"><label htmlFor="password">Password</label>
              <input id="password" type="password" required minLength={8} maxLength={64} autoComplete="new-password" value={f.password} onChange={e => set('password', e.target.value)} />
              <div className="help">At least 8 characters.</div></div>
          </div>
          <button className="btn btn-primary w-full justify-center py-[11px] mt-5" type="submit" disabled={busy === 'signup'}>
            {busy === 'signup' ? 'Creating your account…' : 'Create operator account'}</button>
        </form>
        <div className="mt-[18px] p-3 bg-saffron-soft rounded-[10px] text-[12.5px] text-[#7A4510]">
          <div className="font-bold mb-1">What happens next</div>
          Add your PAN + bank details and documents on the Verification page. Approval needs at least <b>Bronze</b> (PAN + bank + mobile).
          Add Aadhaar for <b>Silver</b>, or GST + Udyam for <b>Gold</b>. Travellers see your tier on every trip.
        </div>
        <p className="text-center mt-3 text-[12.5px] text-muted">By creating an account you agree to our <a className="link" href="/terms" target="_blank">Terms</a> and <a className="link" href="/privacy" target="_blank">Privacy policy</a>.</p>
        <p className="text-center mt-2 text-[13px]">Already listed? <Link className="link" to="/partner/login">Sign in</Link> · <a className="link" href="/">PakkaTrip for travellers</a></p>
      </div>
    </section>
  )
}
