import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useFeedback } from '../components/feedback'
import { api } from '../lib/api'
import { fmtDate, fmtDay, inr, plural } from '../lib/format'
import { FlowSteps } from './Book'
import { Spinner } from './parts'
import { DummyQR, PIcon, rememberTicket, ticketKey } from './shared'

export function TicketCard({ t }) {
  const pill = { upcoming: <span className="pill green">Confirmed</span>, completed: <span className="pill navy">Completed</span>, cancelled: <span className="pill red">Cancelled</span> }[t.display]
  return (
    <div className="ticket" id="ticket">
      <div className="ticket-head"><span className="brand" style={{ fontSize: 17 }}><span className="brand-mark" style={{ width: 28, height: 28 }}><PIcon name="check" size={16} /></span><span>Pakka<b>Trip</b> e-ticket</span></span>{pill}</div>
      <div className="ticket-body">
        <div>
          <div className="help" style={{ margin: 0 }}>Booking ID</div><div style={{ fontFamily: 'ui-monospace,Consolas,monospace', fontSize: 20, fontWeight: 700 }}>{t.code}</div>
          <div className="ticket-route" style={{ marginTop: 10 }}>{t.from_city} <PIcon name="arrow" size={20} /> {t.to_city}</div>
          <div style={{ fontWeight: 600 }}>{t.title}</div>
          <div className="ticket-grid">
            <div><small>Departure</small>{fmtDay(t.travel_date)}</div>
            <div><small>Seats</small>{t.seats}</div>
            <div><small>Lead traveller</small>{t.lead_name}</div>
            <div><small>Mobile</small>{t.phone}</div>
            {t.co_travellers.length > 0 && <div style={{ gridColumn: '1/-1' }}><small>Co-travellers</small>{t.co_travellers.join(', ')}</div>}
            <div style={{ gridColumn: '1/-1' }}><small>Pickup</small>{t.pickup_point || 'Shared by the operator before departure'}</div>
            <div><small>Operator</small>{t.operator}<div className="help" style={{ margin: 0 }}>{t.operator_phone}</div></div>
            <div><small>Amount paid</small>{inr(t.total)}<div className="help" style={{ margin: 0 }}>incl. {inr(t.fee)} fee</div></div>
          </div>
        </div>
        <div className="ticket-qr"><DummyQR text={t.code} /><small>Dummy QR · show booking ID at pickup</small></div>
      </div>
      <div className="ticket-foot">Booked on {fmtDate(t.booked_on)}{t.payment ? ` · paid via ${t.payment}` : ''}. Carry a government photo ID.{' '}
        {t.display === 'cancelled' ? `Cancelled on ${fmtDate(t.cancelled_on)} — refund ${inr(t.refund)}.` : 'Reach the pickup point 30 minutes early.'}</div>
    </div>
  )
}

/** Save the ticket as a standalone HTML file (works offline, prints well). */
function downloadTicket(t) {
  const el = document.getElementById('ticket')
  const css = [...document.styleSheets].map(s => { try { return [...s.cssRules].map(r => r.cssText).join('\n') } catch { return '' } }).join('\n')
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PakkaTrip ticket ${t.code}</title><style>${css} body{padding:20px;background:#F4F6FA}</style></head><body><div class="pub">${el.outerHTML}</div></body></html>`
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
  a.download = `PakkaTrip-ticket-${t.code}.html`
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function Ticket() {
  const { code } = useParams()
  const [params] = useSearchParams()
  const { toast } = useFeedback()
  const [t, setT] = useState(null)
  const [error, setError] = useState(null)
  const isNew = params.get('new') === '1'

  useEffect(() => {
    const key = params.get('key') || ticketKey(code)
    api(`/public/bookings/${code}/` + (key ? `?key=${encodeURIComponent(key)}` : '')).then(d => { setT(d); rememberTicket(d.code, d.key); document.title = `Ticket ${d.code} — PakkaTrip` }, setError)
  }, [code])   // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return (
    <div className="container"><div className="card empty-state" style={{ margin: '30px 0' }}><h3>Ticket not found</h3>
      <p>Log in with the account you booked with, or find your booking with its ID and mobile number.</p><Link className="btn btn-primary" to="/my-bookings">Go to My Bookings</Link></div></div>
  )
  if (!t) return <Spinner />

  return (
    <div className="container">
      {isNew ? <>
        <FlowSteps step={5} />
        <div className="card confirm-hero"><div className="tick"><PIcon name="check" size={38} /></div><h1>Pakka Booking Confirmed!</h1>
          <p>Your {plural(t.seats, 'seat')} on <b>{fmtDay(t.travel_date)}</b> {t.seats > 1 ? 'are' : 'is'} reserved. {t.operator} has been notified, and the e-ticket was sent to {t.email || 'your email'} (demo).</p></div>
      </> : <Link className="link" to="/my-bookings" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', margin: '16px 0' }}><PIcon name="back" size={16} /> My Bookings</Link>}
      <div style={{ marginTop: 18 }}><TicketCard t={t} /></div>
      <div className="ticket-actions">
        <button className="btn btn-primary" onClick={() => { downloadTicket(t); toast('Ticket downloaded') }}><PIcon name="download" size={18} /> Download ticket</button>
        <button className="btn" onClick={() => window.print()}><PIcon name="print" size={18} /> Print</button>
        <Link className="btn btn-outline" to="/my-bookings">View My Bookings</Link>
      </div>
    </div>
  )
}
