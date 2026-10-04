import { useOutletContext } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { EmptyRow, Icon, LoadError, Loading, StatCard } from '../../components/ui'
import { api } from '../../lib/api'
import { inr, plural, sum } from '../../lib/format'
import { useApi } from '../../lib/useApi'
import { BANK_BADGE, PAYOUT_BADGE } from '../operator/Bank'

const FINAL = ['processed', 'reversed', 'failed', 'cancelled', 'rejected']
const when = d => d ? new Date(d).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '—'

export default function AdminPayouts() {
  const { data: d, error, reload } = useApi('/admin/payouts/')
  const { open, confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const changed = msg => { toast(msg); reload(); refreshCounts() }

  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />
  const route = d.mode === 'route'
  const ready = o => o.bank?.status === 'verified' && (route ? o.bank.route_ready : o.bank.payouts_ready)

  const verify = o => confirm('Verify bank account?', <>
    <p className="m-0">Approve <b>{o.bank.holder_name}</b> · {o.bank.account} at {o.bank.bank_name} ({o.bank.ifsc}) for <b>{o.name}</b>?</p>
    <p className="sub mb-0">This creates the {route ? 'Razorpay Route linked account' : 'RazorpayX contact and fund account'} used to pay them.
      Check the name matches the operator's documents.</p></>, 'Verify', async () => {
    await api(`/admin/bank-accounts/${o.id}/verify/`, { method: 'POST' })
    changed(`${o.name}'s bank account verified`)
  }, { submitClass: 'btn-primary' })

  const reject = o => open({
    title: 'Send bank details back', submitLabel: 'Send back', submitClass: 'btn-danger',
    body: <><p className="mt-0">Tell <b>{o.name}</b> what to fix. They'll see this message.</p>
      <label>Reason</label><textarea name="reason" required minLength={5} maxLength={200} rows={3} placeholder="e.g. Account holder name doesn't match the business name" /></>,
    onSubmit: async f => { await api(`/admin/bank-accounts/${o.id}/reject/`, { method: 'POST', body: { reason: f.reason } }); changed('Sent back to the operator') },
  })

  const pay = o => confirm(`Pay ${inr(o.due)}?`, <>
    <p className="m-0">Send <b>{inr(o.due)}</b> for {plural(o.due_count, 'completed booking')} to <b>{o.name}</b> — {o.bank.account}, {o.bank.bank_name}.</p>
    {d.test_mode && <p className="sub mb-0">Test mode: no real money moves.</p>}</>, `Pay ${inr(o.due)}`, async () => {
    const p = await api('/admin/payouts/', { method: 'POST', body: { operator_id: o.id } })
    changed(`Payout of ${inr(p.amount)} to ${o.name}: ${PAYOUT_BADGE[p.status]?.[1] || p.status}`)
  }, { submitClass: 'btn-green' })

  const refresh = async p => {
    try { const r = await api(`/admin/payouts/${p.id}/refresh/`, { method: 'POST' }); changed(`Payout ${PAYOUT_BADGE[r.status]?.[1] || r.status}`) }
    catch (err) { toast(err.message, true) }
  }

  const waiting = d.operators.filter(o => o.bank?.status === 'pending').length
  return (
    <>
      <div className="stats">
        <StatCard icon="wallet" tone="green" label="Due to operators now" value={inr(sum(d.operators, o => o.due))} note="Completed trips not paid out yet" />
        <StatCard icon="calendar" tone="navy" label="After upcoming trips" value={inr(sum(d.operators, o => o.upcoming))} note="Confirmed, trip not run yet" />
        <StatCard icon="clock" tone="amber" label="In transit" value={inr(sum(d.operators, o => o.in_flight))} note="Payouts not settled yet" />
        <StatCard icon="shield" tone="saffron" label="Bank accounts to verify" value={waiting} note={waiting ? 'Payouts paused for these operators' : 'All caught up'} />
      </div>

      <div className="banner" style={route ? {} : { background: 'var(--color-navy-soft)', color: 'var(--color-navy-2)' }}>
        <Icon name="info" />
        <span>{route
          ? <><b>Route mode:</b> each paid booking's operator share is transferred automatically, held until the trip completes. Bookings that couldn't be transferred appear below as due.</>
          : <><b>Payouts mode:</b> send each operator what's due by RazorpayX after their trips complete. Change the mode in Settings.</>}
          {!route && !d.razorpayx_ready && <> <b>Set RAZORPAYX_ACCOUNT_NUMBER in backend/.env before sending payouts.</b></>}
          {d.test_mode && ' Test mode — no real money moves.'}</span>
      </div>

      <div className="card">
        <div className="card-head"><h3>Operators</h3></div>
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Operator</th><th>Bank account</th><th className="num">Due now</th><th className="num">Upcoming</th><th className="num">Paid out</th><th className="num">Actions</th></tr></thead>
          <tbody>
            {d.operators.map(o => (
              <tr key={o.id}>
                <td><b>{o.name}</b>{!o.verified && <div className="sub">Operator not verified</div>}</td>
                <td>{o.bank
                  ? <><span className={`badge ${BANK_BADGE[o.bank.status][0]}`}>{BANK_BADGE[o.bank.status][1]}</span>
                    <div className="sub">{o.bank.holder_name} · {o.bank.account} · {o.bank.bank_name}</div>
                    {o.bank.status === 'verified' && !ready(o) && <div className="sub" style={{ color: 'var(--color-amber)' }}>Verify again to set up {route ? 'Route' : 'payouts'}</div>}</>
                  : <span className="sub">Not added</span>}</td>
                <td className="num"><b>{inr(o.due)}</b>{o.due_count > 0 && <div className="sub">{plural(o.due_count, 'booking')}</div>}</td>
                <td className="num">{inr(o.upcoming)}</td>
                <td className="num">{inr(o.paid)}</td>
                <td><div className="actions">
                  {o.bank && (o.bank.status === 'pending' || (o.bank.status === 'verified' && !ready(o))) &&
                    <button className="btn btn-sm btn-ghost-green" onClick={() => verify(o)}>Verify</button>}
                  {o.bank?.status === 'pending' && <button className="btn btn-sm btn-ghost-red" onClick={() => reject(o)}>Send back</button>}
                  {o.due > 0 && o.bank?.status === 'verified' && o.bank.payouts_ready &&
                    <button className="btn btn-sm btn-green" onClick={() => pay(o)}>Pay {inr(o.due)}</button>}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </div>

      <div className="card">
        <div className="card-head"><h3>Payout history</h3></div>
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Date</th><th>Operator</th><th className="num">Amount</th><th>To account</th><th>Status</th><th>UTR</th><th className="num"></th></tr></thead>
          <tbody>
            {d.history.length ? d.history.map(p => (
              <tr key={p.id}>
                <td>{when(p.created_at)}</td><td>{p.operator}<div className="sub">{plural(p.bookings, 'booking')} · {p.mode}</div></td>
                <td className="num"><b>{inr(p.amount)}</b></td><td>{p.account}</td>
                <td><span className={`badge ${PAYOUT_BADGE[p.status]?.[0] || 'b-navy'}`}>{PAYOUT_BADGE[p.status]?.[1] || p.status}</span>
                  {p.failure_reason && <div className="sub">{p.failure_reason}</div>}</td>
                <td>{p.utr || '—'}</td>
                <td>{!FINAL.includes(p.status) && <button className="btn btn-sm" onClick={() => refresh(p)}>Refresh</button>}</td>
              </tr>
            )) : <EmptyRow cols={7}>No payouts yet.</EmptyRow>}
          </tbody>
        </table></div>
      </div>
    </>
  )
}
