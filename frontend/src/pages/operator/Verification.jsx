import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { Icon, LoadError, Loading, TIERS, TierBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useApi } from '../../lib/useApi'

const DOC_BADGE = { pending: ['b-amber', 'Under review'], verified: ['b-green', 'Verified'], rejected: ['b-red', 'Needs changes'] }
const CHECK_FOR = { 'PAN + bank': 'pan_bank', 'Phone OTP': 'phone', GST: 'gst', Udyam: 'udyam', Aadhaar: 'aadhaar' }

const StatusBadge = ({ status }) => status
  ? <span className={`badge ${DOC_BADGE[status][0]}`}>{DOC_BADGE[status][1]}</span>
  : <span className="badge b-grey">Not added</span>

function Row({ title, note, status, children }) {
  return (
    <div className="p-[18px] border-t border-line first:border-t-0">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-[200px]"><b>{title}</b><div className="sub">{note}</div></div>
        {status}
      </div>
      {children}
    </div>
  )
}

function DocForm({ kind, doc, label, placeholder, pattern, help, withFile, onSaved }) {
  const { toast } = useFeedback()
  const [open, setOpen] = useState(!doc || doc.status === 'rejected')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!open) return <button className="btn btn-sm mt-3" type="button" onClick={() => setOpen(true)}>Replace</button>

  async function save(e) {
    e.preventDefault()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    setBusy(true); setError('')
    try {
      const fd = new FormData(form)
      const d = await api(`/operator/verification/documents/${kind}/`, { method: 'PUT', body: withFile ? fd : Object.fromEntries(fd) })
      toast('Submitted. PakkaTrip will review it shortly.')
      setOpen(false); onSaved(d)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <form className="mt-3 flex flex-col gap-2.5 max-w-[520px]" onSubmit={save} noValidate>
      {error && <div className="form-error m-0" role="alert">{error}</div>}
      <div><label htmlFor={`${kind}-number`}>{label}</label>
        <input id={`${kind}-number`} name="number" required pattern={pattern} placeholder={placeholder} autoComplete="off" style={{ textTransform: 'uppercase' }} />
        {help && <div className="help">{help}</div>}</div>
      {withFile && <div><label htmlFor={`${kind}-file`}>Masked Aadhaar copy (JPG, PNG or PDF, up to 5 MB)</label>
        <input id={`${kind}-file`} name="file" type="file" required accept="image/jpeg,image/png,image/webp,application/pdf" />
        <div className="help">Download a <b>masked Aadhaar</b> (first 8 digits hidden) from myaadhaar.uidai.gov.in. It's stored encrypted and only PakkaTrip staff can view it.</div></div>}
      <div className="flex gap-2"><button className="btn btn-navy btn-sm" type="submit" disabled={busy}>{busy ? 'Submitting…' : 'Submit for review'}</button>
        {doc && <button className="btn btn-sm" type="button" onClick={() => setOpen(false)}>Cancel</button>}</div>
    </form>
  )
}

function PhoneOtp({ phone, onVerified }) {
  const [sent, setSent] = useState(false)
  const [devCode, setDevCode] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async fn => { setBusy(true); setError(''); try { await fn() } catch (err) { setError(err.message) } finally { setBusy(false) } }
  const send = () => run(async () => { const d = await api('/operator/verification/phone/otp/', { method: 'POST' }); setSent(true); setDevCode(d.dev_code || '') })
  const verify = () => run(async () => onVerified(await api('/operator/verification/phone/verify/', { method: 'POST', body: { code } })))
  return (
    <div className="mt-3 flex flex-col gap-2 max-w-[420px]">
      {error && <div className="form-error m-0" role="alert">{error}</div>}
      {!sent ? <button className="btn btn-sm self-start" type="button" onClick={send} disabled={busy}>Send code to {phone}</button> : <>
        <div className="flex gap-2">
          <input aria-label="6-digit code from the SMS" inputMode="numeric" maxLength={6} placeholder="6-digit code" autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} />
          <button className="btn btn-navy btn-sm flex-none" type="button" onClick={verify} disabled={busy || code.length !== 6}>Verify</button>
          <button className="btn btn-sm flex-none" type="button" onClick={send} disabled={busy}>Resend</button>
        </div>
        {devCode && <div className="help">Development mode (no SMS sent): your code is <b>{devCode}</b></div>}
      </>}
    </div>
  )
}

export default function OpVerification() {
  const { data: fetched, error, reload } = useApi('/operator/verification/')
  const [override, setOverride] = useState(null)
  const { refreshMe } = useAuth()
  const { toast } = useFeedback()
  if (error) return <LoadError error={error} retry={reload} />
  if (!fetched) return <Loading />
  const d = override && override.operator_id === fetched.operator_id ? override : fetched
  const changed = next => { setOverride({ ...next, can_edit: d.can_edit }); refreshMe().catch(() => {}) }
  const docs = d.documents
  const resubmit = async () => {
    try { changed(await api('/operator/verification/resubmit/', { method: 'POST' })); toast('Application sent for review again') }
    catch (err) { toast(err.message, true) }
  }

  return (
    <>
      {d.status === 'pending' && <div className="banner"><Icon name="clock" size={20} />
        <div>Your application is <b>under review</b>. You can add packages and departures now; travellers see them once PakkaTrip approves you.
          Approval needs at least <b>Bronze</b>.</div></div>}
      {d.status === 'rejected' && <div className="banner" style={{ background: 'var(--color-danger-soft)', color: 'var(--color-danger)' }}>
        <Icon name="alert" size={20} /><div className="flex-1">Your application was sent back: <b>{d.rejection_reason}</b>. Fix the details below, then resubmit.</div>
        {d.can_edit && <button className="btn btn-sm" type="button" onClick={resubmit}>Resubmit</button>}</div>}

      <div className="card">
        <div className="card-head"><h3>Your verification tier</h3><TierBadge tier={d.tier} /></div>
        <div className="p-[18px] grid gap-3 grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
          {TIERS.map(([id, label, needs]) => {
            const got = needs.filter(n => d.checks[CHECK_FOR[n]]).length
            return (
              <div key={id} className={`rounded-xl border p-3.5 ${d.tier === id ? 'border-navy bg-navy-soft' : 'border-line'}`}>
                <div className="flex items-center justify-between"><span className={`badge b-${id}`}>{label}</span><span className="sub">{got}/{needs.length}</span></div>
                <ul className="mt-2.5 flex flex-col gap-1.5 text-[13.5px]">
                  {needs.map(n => <li key={n} className="flex items-center gap-2">
                    <span className={d.checks[CHECK_FOR[n]] ? 'text-leaf' : 'text-muted'}><Icon name={d.checks[CHECK_FOR[n]] ? 'check' : 'clock'} size={15} /></span>{n}</li>)}
                </ul>
              </div>
            )
          })}
        </div>
        <div className="table-foot"><span>Travellers see your tier on every trip. GST is not required: you can reach Silver or Bronze without it.</span></div>
      </div>

      <div className="card">
        <div className="card-head"><h3>Checks</h3>{!d.can_edit && <span className="sub">Only the business owner can submit documents.</span>}</div>
        <Row title="PAN + bank account" note="Needed for every tier. Added on the Bank & Payouts page and verified by PakkaTrip."
          status={<StatusBadge status={d.bank?.status} />}>
          <div className="mt-2 text-[13.5px]">{d.bank ? <>{d.bank.bank_name} · {d.bank.account} · PAN {d.bank.pan}
            {d.bank.status === 'rejected' && <div className="sub" style={{ color: 'var(--color-danger)' }}>{d.bank.rejection_reason}</div>}</> : null}
            <Link className="link ml-2" to="/operator/bank">{d.bank ? 'Bank & Payouts →' : 'Add PAN + bank details →'}</Link></div>
        </Row>
        <Row title="Mobile number (OTP)" note={`Bronze tier. ${d.phone.number}`} status={<StatusBadge status={d.phone.verified ? 'verified' : null} />}>
          {!d.phone.verified && <PhoneOtp phone={d.phone.number} onVerified={next => { changed(next); toast('Mobile number verified') }} />}
        </Row>
        <Row title="Aadhaar (owner)" note={`Silver tier. We keep only the last 4 digits and an encrypted masked copy.${docs.aadhaar ? ` On file: ${docs.aadhaar.number}` : ''}`}
          status={<StatusBadge status={docs.aadhaar?.status} />}>
          {docs.aadhaar?.status === 'rejected' && <div className="sub mt-1" style={{ color: 'var(--color-danger)' }}>{docs.aadhaar.rejection_reason}</div>}
          {d.can_edit && <DocForm kind="aadhaar" doc={docs.aadhaar} label="Last 4 digits of Aadhaar" placeholder="1234" pattern="[0-9]{4}"
            help="Never enter the full Aadhaar number." withFile onSaved={changed} />}
        </Row>
        <Row title="GST registration" note={`Gold tier (optional).${docs.gst ? ` On file: ${docs.gst.number}` : ''}`} status={<StatusBadge status={docs.gst?.status} />}>
          {docs.gst?.status === 'rejected' && <div className="sub mt-1" style={{ color: 'var(--color-danger)' }}>{docs.gst.rejection_reason}</div>}
          {d.can_edit && <DocForm kind="gst" doc={docs.gst} label="GSTIN" placeholder="07ABCDE1234F1Z5" pattern="[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][1-9A-Za-z][Zz][0-9A-Za-z]"
            help="15 characters, as on your GST certificate." onSaved={changed} />}
        </Row>
        <Row title="Udyam (MSME) registration" note={`Gold tier, together with GST.${docs.udyam ? ` On file: ${docs.udyam.number}` : ''}`} status={<StatusBadge status={docs.udyam?.status} />}>
          {docs.udyam?.status === 'rejected' && <div className="sub mt-1" style={{ color: 'var(--color-danger)' }}>{docs.udyam.rejection_reason}</div>}
          {d.can_edit && <DocForm kind="udyam" doc={docs.udyam} label="Udyam registration number" placeholder="UDYAM-DL-01-0012345"
            pattern="[Uu][Dd][Yy][Aa][Mm]-[A-Za-z]{2}-[0-9]{2}-[0-9]{7}" onSaved={changed} />}
        </Row>
      </div>
    </>
  )
}
