import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { LoadError, Loading } from '../../components/ui'
import { api } from '../../lib/api'
import { inr } from '../../lib/format'
import { useApi } from '../../lib/useApi'

const feeFor = (amount, rate, min) => Math.max(Number(min) || 0, Math.round(amount * (Number(rate) || 0) / 100))

export default function AdminSettings() {
  const { data, error, reload } = useApi('/admin/settings/')
  const { confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const [draft, setDraft] = useState(null)

  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />
  const s = draft || data

  async function save(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    try {
      await api('/admin/settings/', { method: 'PUT', body: { fee_rate: Number(s.fee_rate), fee_min: Number(s.fee_min), require_verified: s.require_verified, payout_mode: s.payout_mode } })
      setDraft(null); reload(); toast('Settings saved')
    } catch (err) { toast(err.message, true) }
  }
  const reset = () => confirm('Reset demo data?', 'This replaces every operator, package, departure, booking and review with the original demo data.', 'Reset', async () => {
    await api('/admin/reset-demo/', { method: 'POST' })
    toast('Demo data restored'); refreshCounts()
  })
  const set = patch => setDraft({ ...s, ...patch })

  return (
    <>
      <div className="card max-w-[640px]">
        <div className="card-head"><h3>Convenience fee</h3></div>
        <form className="p-[18px]" onSubmit={save} noValidate>
          <div className="form-grid">
            <div><label>Fee rate (%)</label><input type="number" required min={0} max={20} step={0.1} value={s.fee_rate} onChange={e => set({ fee_rate: e.target.value })} /></div>
            <div><label>Minimum fee (₹)</label><input type="number" required min={0} max={999} step={1} value={s.fee_min} onChange={e => set({ fee_min: e.target.value })} /></div>
            <div className="full"><div className="help">Charged to customers on online bookings only. New rates apply to new bookings; past bookings keep the fee they paid.
              Example: a ₹6,499 booking pays <b>{inr(feeFor(6499, s.fee_rate, s.fee_min))}</b>.</div></div>
            <div className="full"><label className="check"><input type="checkbox" checked={s.require_verified} onChange={e => set({ require_verified: e.target.checked })} /> Only approve packages from verified operators</label></div>
          </div>
          <div className="mt-4"><button className="btn btn-navy" type="submit">Save settings</button></div>
        </form>
      </div>
      <div className="card max-w-[640px]">
        <div className="card-head"><h3>Operator payouts</h3></div>
        <form className="p-[18px]" onSubmit={save} noValidate>
          <label className="check items-start"><input type="radio" name="payout_mode" checked={s.payout_mode === 'payouts'} onChange={() => set({ payout_mode: 'payouts' })} />
            <span><b>RazorpayX payouts</b> — you send each operator what's due from Admin → Payouts after their trips complete. Works on any Razorpay account.</span></label>
          <label className="check items-start mt-2.5"><input type="radio" name="payout_mode" checked={s.payout_mode === 'route'} onChange={() => set({ payout_mode: 'route' })} />
            <span><b>Razorpay Route (automatic split)</b> — each payment is split as it's captured: the operator's share goes to their linked account, held until the trip completes.
              Razorpay must enable Route on your account first.</span></label>
          <div className="help mt-2">Switching modes applies to new bookings. Operators' bank accounts need verifying again in the new mode (Admin → Payouts).</div>
          <div className="mt-4"><button className="btn btn-navy" type="submit">Save settings</button></div>
        </form>
      </div>
      {data.can_reset && (
        <div className="card max-w-[640px]">
          <div className="card-head"><h3>Demo data</h3></div>
          <div className="p-[18px] flex gap-3.5 items-center flex-wrap">
            <div className="flex-1 min-w-[220px] sub">Restore the original demo operators, packages, departures, bookings and reviews. Available in development only.</div>
            <button className="btn btn-ghost-red" onClick={reset}>Reset demo data</button>
          </div>
        </div>
      )}
    </>
  )
}
