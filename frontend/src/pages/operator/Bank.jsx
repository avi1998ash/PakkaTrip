import { useState } from 'react'
import { useFeedback } from '../../components/feedback'
import { EmptyRow, Icon, LoadError, Loading, StatCard } from '../../components/ui'
import { api } from '../../lib/api'
import { inr, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export const PAYOUT_BADGE = {
  processed: ['b-green', 'Paid'], processing: ['b-navy', 'In transit'], pending: ['b-navy', 'In transit'], queued: ['b-amber', 'Queued'],
  reversed: ['b-red', 'Returned by bank'], failed: ['b-red', 'Failed'], cancelled: ['b-red', 'Cancelled'], rejected: ['b-red', 'Rejected'],
}
export const BANK_BADGE = { pending: ['b-amber', 'Awaiting verification'], verified: ['b-green', 'Verified'], rejected: ['b-red', 'Needs changes'] }
const BUSINESS_TYPES = [['proprietorship', 'Proprietorship'], ['individual', 'Individual'], ['partnership', 'Partnership'], ['llp', 'LLP'], ['private_limited', 'Private limited']]
const when = d => d ? new Date(d).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'

function BankForm({ bank, onSaved, onCancel }) {
  const { toast } = useFeedback()
  const [ifscInfo, setIfscInfo] = useState(bank ? { bank: bank.bank_name, branch: bank.branch } : null)
  const [ifscError, setIfscError] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function lookup(e) {
    const code = e.target.value.trim().toUpperCase()
    setIfscInfo(null); setIfscError('')
    if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(code)) { if (code) setIfscError('IFSC is 11 characters, like HDFC0001234.'); return }
    try { setIfscInfo(await api(`/operator/ifsc/${code}/`)) } catch (err) { setIfscError(err.message) }
  }

  async function save(e) {
    e.preventDefault()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    const d = Object.fromEntries(new FormData(form))
    if (d.account_number !== d.confirm_account_number) { setError("Account numbers don't match."); return }
    setSaving(true); setError('')
    try {
      await api('/operator/bank-account/', { method: 'PUT', body: d })
      toast('Bank details saved — PakkaTrip will verify them shortly')
      onSaved()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }

  return (
    <form className="p-[18px]" onSubmit={save} noValidate>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-grid">
        <div className="full"><label>Account holder name</label>
          <input name="holder_name" required maxLength={100} defaultValue={bank?.holder_name} placeholder="Exactly as on the bank account" autoComplete="off" /></div>
        <div><label>Account number</label>
          <input name="account_number" required inputMode="numeric" pattern="[0-9]{9,18}" title="9 to 18 digits" autoComplete="off" placeholder={bank ? `Ends in ${bank.last4} — re-enter to change` : ''} /></div>
        <div><label>Re-enter account number</label>
          <input name="confirm_account_number" required inputMode="numeric" pattern="[0-9]{9,18}" title="9 to 18 digits" autoComplete="off" onPaste={e => e.preventDefault()} /></div>
        <div><label>IFSC</label>
          <input name="ifsc" required maxLength={11} pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}" title="Like HDFC0001234" defaultValue={bank?.ifsc} onBlur={lookup} style={{ textTransform: 'uppercase' }} />
          {ifscInfo && <div className="help" style={{ color: 'var(--color-leaf)' }}><Icon name="check" size={13} /> {ifscInfo.bank}, {ifscInfo.branch}</div>}
          {ifscError && <div className="help" style={{ color: 'var(--color-danger)' }}>{ifscError}</div>}</div>
        <div><label>Account type</label>
          <select name="account_type" defaultValue={bank?.account_type || 'current'}><option value="current">Current</option><option value="savings">Savings</option></select></div>
        <div><label>PAN</label>
          <input name="pan" required maxLength={10} pattern="[A-Za-z]{5}[0-9]{4}[A-Za-z]" title="Like ABCDE1234F" autoComplete="off" placeholder={bank ? `${bank.pan} — re-enter to change` : 'ABCDE1234F'} style={{ textTransform: 'uppercase' }} /></div>
        <div><label>Business type</label>
          <select name="business_type" defaultValue={bank?.business_type || 'proprietorship'}>{BUSINESS_TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
        <div className="full"><label>Registered business address</label>
          <input name="address_line" required maxLength={200} defaultValue={bank?.address_line} placeholder="Building, street, area" /></div>
        <div><label>City</label><input name="address_city" required maxLength={60} defaultValue={bank?.address_city} /></div>
        <div><label>State</label><input name="address_state" required maxLength={60} defaultValue={bank?.address_state} /></div>
        <div><label>PIN code</label><input name="pincode" required inputMode="numeric" pattern="[1-9][0-9]{5}" title="6-digit PIN code" defaultValue={bank?.pincode} /></div>
        <div className="full"><div className="help"><Icon name="shield" size={13} /> Your account number and PAN are encrypted. PakkaTrip staff only ever see the last 4 characters.
          {bank?.status === 'verified' && <> <b>Changing these details pauses payouts until we verify the new account.</b></>}</div></div>
      </div>
      <div className="mt-4 flex gap-2.5">
        <button className="btn btn-navy" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save bank details'}</button>
        {onCancel && <button className="btn" type="button" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}

export default function OpBank() {
  const { data: d, error, reload } = useApi('/operator/bank-account/')
  const [editing, setEditing] = useState(false)
  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />
  const b = d.bank
  const route = d.mode === 'route'

  return (
    <>
      <div className="stats">
        <StatCard icon="wallet" tone="green" label="Due to you now" value={inr(d.due)} note={d.due_count ? `${plural(d.due_count, 'completed booking')} · sent by PakkaTrip` : 'Nothing waiting'} />
        <StatCard icon="calendar" tone="navy" label="After upcoming trips" value={inr(d.upcoming)} note="Becomes due when each trip completes" />
        <StatCard icon="clock" tone="amber" label="In transit" value={inr(d.in_flight)} note="Payouts on the way to your bank" />
        <StatCard icon="check" tone="saffron" label="Paid out" value={inr(d.paid)} note="Total received so far" />
      </div>

      {!b && <div className="banner"><Icon name="alert" /> Add your bank account to receive money from online bookings.</div>}
      {b?.status === 'pending' && <div className="banner"><Icon name="clock" /> Your bank details are being verified. Payouts are paused until then — this usually takes one working day.</div>}
      {b?.status === 'rejected' && <div className="banner" style={{ background: 'var(--color-danger-soft)', color: 'var(--color-danger)' }}>
        <Icon name="alert" /> We couldn't verify your bank details: {b.rejection_reason}. Please correct them below.</div>}

      <div className="card max-w-[760px]">
        <div className="card-head"><h3>Bank account</h3>{b && <span className={`badge ${BANK_BADGE[b.status][0]}`}>{BANK_BADGE[b.status][1]}</span>}</div>
        {!b || editing || b.status === 'rejected'
          ? (d.can_edit
            ? <BankForm bank={b} onSaved={() => { setEditing(false); reload() }} onCancel={b && b.status !== 'rejected' ? () => setEditing(false) : null} />
            : <div className="p-[18px] sub">Only the business owner can add or change bank details.</div>)
          : <div className="p-[18px]">
            <dl className="grid grid-cols-[160px_1fr] gap-y-2 gap-x-4 m-0 text-[14px]">
              <dt className="sub">Account holder</dt><dd className="m-0"><b>{b.holder_name}</b></dd>
              <dt className="sub">Account</dt><dd className="m-0">{b.account} · {b.account_type === 'current' ? 'Current' : 'Savings'}</dd>
              <dt className="sub">Bank</dt><dd className="m-0">{b.bank_name}, {b.branch} <span className="sub">({b.ifsc})</span></dd>
              <dt className="sub">PAN</dt><dd className="m-0">{b.pan}</dd>
              <dt className="sub">Address</dt><dd className="m-0">{b.address_line}, {b.address_city}, {b.address_state} {b.pincode}</dd>
              {b.verified_at && <><dt className="sub">Verified</dt><dd className="m-0">{when(b.verified_at)}</dd></>}
            </dl>
            {d.can_edit && <button className="btn mt-4" onClick={() => setEditing(true)}>Change bank details</button>}
          </div>}
      </div>

      <div className="card">
        <div className="card-head"><h3>Payouts</h3>
          <span className="sub">{route
            ? 'Each online booking is transferred to your account automatically and released after the trip runs.'
            : 'PakkaTrip sends what you are owed by bank transfer after each trip completes.'}</span></div>
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Date</th><th className="num">Amount</th><th>To account</th><th>Bookings</th><th>Status</th><th>Bank reference (UTR)</th></tr></thead>
          <tbody>
            {d.payouts.length ? d.payouts.map(p => (
              <tr key={p.id}>
                <td>{when(p.created_at)}</td><td className="num"><b>{inr(p.amount)}</b></td><td>{p.account}</td><td>{p.bookings}</td>
                <td><span className={`badge ${PAYOUT_BADGE[p.status]?.[0] || 'b-navy'}`}>{PAYOUT_BADGE[p.status]?.[1] || p.status}</span>
                  {p.failure_reason && <div className="sub">{p.failure_reason}</div>}</td>
                <td>{p.utr || '—'}</td>
              </tr>
            )) : <EmptyRow cols={6}>No payouts yet.</EmptyRow>}
          </tbody>
        </table></div>
        <div className="table-foot"><span>You receive the full package price of every online booking — PakkaTrip takes no commission. Offline bookings are paid to you directly.</span></div>
      </div>
    </>
  )
}
