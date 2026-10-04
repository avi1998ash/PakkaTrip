import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useFeedback } from '../components/feedback'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, fmtDate, fmtDay, inr, plural } from '../lib/format'
import { PIcon, rememberTicket, savedTickets } from './shared'

export default function MyBookings() {
  const { user } = useAuth()
  const me = user?.role === 'traveller' ? user : null
  const { open, toast } = useFeedback()
  const navigate = useNavigate()
  const [list, setList] = useState(null)
  const [tab, setTab] = useState('upcoming')
  const [find, setFind] = useState({ code: '', phone: '' })

  const load = useCallback(() => api('/public/bookings/lookup/', { method: 'POST', body: { items: savedTickets() } }).then(setList, e => toast(e.message, true)), [toast])
  useEffect(() => { document.title = 'My Bookings — PakkaTrip'; load() }, [load, me?.id])

  const keyFor = b => b.key
  const replace = t => { rememberTicket(t.code, t.key); setList(l => l.map(x => (x.code === t.code ? t : x))) }

  const cancel = b => {
    const q = b.refund_quote
    open({ title: `Cancel booking ${b.code}`, submitLabel: 'Yes, cancel booking', submitClass: 'btn-danger', cancelLabel: 'Keep my booking', body: (
      <div className="pub">
        <p style={{ margin: '0 0 12px' }}><b>{b.title}</b> · {fmtDay(b.travel_date)} · {plural(b.seats, 'seat')}</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="line"><span>Days before departure</span><span>{q.days}</span></div>
          <div className="line"><span>Policy</span><span>{q.label}</span></div>
          <div className="line"><span>Package amount</span><span>{inr(b.amount)}</span></div>
          <div className="line"><span>Refund ({Number(q.pct)}%)</span><span>{inr(q.amount)}</span></div>
          <div className="line"><span>Convenience fee</span><span>Non-refundable ({inr(b.fee)})</span></div>
          <div className="line total"><span>You get back</span><span style={{ color: Number(q.amount) ? 'var(--green)' : 'var(--red)' }}>{inr(q.amount)}</span></div>
        </div>
        <p className="help">Your {b.seats > 1 ? 'seats go' : 'seat goes'} back to the operator straight away. Refunds go back to your original payment method, usually within 5–7 working days.</p>
      </div>
    ), onSubmit: async () => {
      const t = await api(`/public/bookings/${b.code}/cancel/`, { method: 'POST', body: { key: keyFor(b) } })
      replace(t); setTab('cancelled'); toast(`Booking cancelled. Refund of ${inr(t.refund)} initiated.`)
    } })
  }

  const review = b => open({ title: 'Rate your trip', submitLabel: 'Submit review', body: (
    <div className="pub">
      <p style={{ margin: '0 0 10px' }}><b>{b.title}</b> with {b.operator}</p>
      <label>Your rating</label>
      <div className="star-input">{[5, 4, 3, 2, 1].flatMap(n => [
        <input key={`i${n}`} type="radio" name="rating" id={`st${n}`} value={n} defaultChecked={n === 5} required />,
        <label key={`l${n}`} htmlFor={`st${n}`} title={`${n} stars`}>★</label>])}</div>
      <label htmlFor="rvText" style={{ marginTop: 12 }}>Your review</label>
      <textarea id="rvText" name="text" required minLength={10} maxLength={400} placeholder="How was the bus, stay, food and the trip captain?" />
    </div>
  ), onSubmit: async d => {
    const t = await api(`/public/bookings/${b.code}/review/`, { method: 'POST', body: { key: keyFor(b), rating: Number(d.rating), text: d.text } })
    replace(t); toast('Thanks! Your review is live and the operator can reply to it.')
  } })

  async function findBooking(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    try {
      const r = await api('/public/bookings/find/', { method: 'POST', body: { code: find.code.trim().toUpperCase(), phone: find.phone.trim() } })
      rememberTicket(r.code, r.key); toast(`Found ${r.code}`); navigate(`/ticket/${r.code}`)
    } catch (err) { toast(err.message, true) }
  }

  const groups = { upcoming: [], completed: [], cancelled: [] }
  ;(list || []).forEach(b => groups[b.display].push(b))
  groups.upcoming.sort((a, b) => String(a.travel_date).localeCompare(String(b.travel_date)))

  const card = b => (
    <div key={b.code} className="card bk-card">
      <div className="bk-top"><div><div className="help" style={{ margin: 0, fontFamily: 'ui-monospace,Consolas,monospace' }}>{b.code}</div><h3>{b.title}</h3>
        <div className="route" style={{ marginTop: 2 }}>{b.from_city} → {b.to_city}</div></div>
        {{ upcoming: b.status === 'pending_confirmation' ? <span className="pill amber">Awaiting confirmation</span> : <span className="pill green">Confirmed</span>,
          completed: <span className="pill navy">Completed</span>, cancelled: <span className="pill red">Cancelled</span> }[b.display]}</div>
      <div className="bk-meta">
        <div><small>Departure</small>{fmtDay(b.travel_date)}</div><div><small>Duration</small>{durationLabel(b.nights)}</div>
        <div><small>Seats</small>{b.seats}</div><div><small>Amount paid</small>{inr(b.total)}</div>
      </div>
      {b.display === 'cancelled' && <div className="refund-note">Cancelled on {fmtDate(b.cancelled_on)}{b.cancelled_by && b.cancelled_by !== 'customer' ? ' by the operator' : ''}. Refund of <b>{inr(b.refund)}</b> initiated to your original payment method.</div>}
      <div className="bk-actions">
        <Link className="btn btn-sm" to={`/ticket/${b.code}`}><PIcon name="ticket" size={15} /> View ticket</Link>
        {b.display === 'upcoming' && <Link className="btn btn-sm" to={`/trips/${b.package_id}`}>Trip details</Link>}
        {b.can_cancel && <button className="btn btn-sm btn-ghost-red" onClick={() => cancel(b)}>Cancel booking</button>}
        {b.can_review && <button className="btn btn-sm btn-primary" onClick={() => review(b)}><PIcon name="star" size={15} /> Rate your trip</button>}
        {b.reviewed && <span className="pill green">Reviewed — thank you!</span>}
      </div>
    </div>
  )

  return (
    <div className="container" style={{ padding: '20px 16px 40px' }}>
      <div className="sec-head"><div><h2>My Bookings</h2><p>{me ? `Signed in as ${me.email}` : 'Bookings made on this device as a guest.'}</p></div>
        {!me && <Link className="btn btn-navy btn-sm" to="/account?next=/my-bookings">Log in to see all</Link>}</div>
      <div className="tabs" role="tablist">{[['upcoming', 'Upcoming'], ['completed', 'Completed'], ['cancelled', 'Cancelled']].map(([k, t]) => (
        <button key={k} className={`tab ${tab === k ? 'active' : ''}`} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t}<span className="n">{groups[k].length}</span></button>))}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {!list ? <div className="card empty-state">Loading your bookings…</div> : groups[tab].length ? groups[tab].map(card) : (
          <div className="card empty-state"><h3>No {tab} bookings</h3><p>{tab === 'upcoming' ? 'Your next trip is just a search away.' : 'Nothing here yet.'}</p><Link className="btn btn-primary" to="/search">Explore trips</Link></div>
        )}
      </div>
      <form className="card panel" style={{ marginTop: 20 }} onSubmit={findBooking} noValidate>
        <h2 style={{ fontSize: 16 }}>Find a booking</h2>
        <p className="help" style={{ margin: '-6px 0 12px' }}>Booked as a guest on another device? Enter the booking ID and mobile number.</p>
        <div className="form-grid two">
          <div><label>Booking ID</label><input type="text" required placeholder="PT24123" value={find.code} onChange={e => setFind({ ...find, code: e.target.value })} /></div>
          <div><label>Mobile number</label><input type="tel" required pattern="[6-9][0-9]{9}" placeholder="10-digit mobile" value={find.phone} onChange={e => setFind({ ...find, phone: e.target.value })} /></div>
        </div>
        <button className="btn btn-navy" type="submit" style={{ marginTop: 12 }}>Find booking</button>
      </form>
    </div>
  )
}
