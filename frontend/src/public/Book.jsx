import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, fmtDate, fmtDay, inr, plural } from '../lib/format'
import { ErrorBox, Spinner } from './parts'
import { PolicyTable } from './PublicLayout'
import { Bar, CoverImg, MAX_SEATS, PIcon, qs, rememberTicket, SeatPill, seatText, Verified } from './shared'
import { feeFor } from './Trip'

const STEPS = ['Travellers', 'Review', 'Payment', 'Confirmed']
export const FlowSteps = ({ step }) => (
  <div className="flow-steps">{STEPS.map((t, i) => <div key={t} data-n={i + 1} className={i + 1 < step ? 'done' : i + 1 === step ? 'now' : ''}>{t}</div>)}</div>
)
const BANKS = ['State Bank of India', 'HDFC Bank', 'ICICI Bank', 'Axis Bank', 'Punjab National Bank', 'Bank of Baroda', 'Kotak Mahindra Bank']

export default function Book() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const me = user?.role === 'traveller' ? user : null
  const [p, setP] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [step, setStep] = useState(1)
  const [depId, setDepId] = useState(null)
  const [pax, setPax] = useState(Math.max(1, Math.min(MAX_SEATS, Number(params.get('pax')) || 1)))
  const [lead, setLead] = useState({ name: me?.name || '', phone: me?.phone || '', email: me?.email || '' })
  const [others, setOthers] = useState([])
  const [quote, setQuote] = useState(null)
  const [agree, setAgree] = useState(false)
  const [method, setMethod] = useState('upi')
  const [upiApp, setUpiApp] = useState('GPay')
  const [error, setError] = useState('')
  const [paying, setPaying] = useState(false)
  const [guestOk, setGuestOk] = useState(false)

  useEffect(() => {
    Promise.all([api(`/public/packages/${id}/`), api('/public/config/')]).then(([d, c]) => {
      setP(d); setCfg(c)
      document.title = `Book ${d.title} — PakkaTrip`
      const want = Number(params.get('dep'))
      const open = d.departures.filter(x => !x.blocked && x.available > 0)
      setDepId((open.find(x => x.id === want) || open[0])?.id ?? null)
    }, setLoadError)
  }, [id])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'smooth' }) }, [step])

  if (loadError) return <ErrorBox error={loadError} />
  if (!p || !cfg) return <Spinner />

  const dep = p.departures.find(d => d.id === depId)
  const maxPax = dep ? Math.min(MAX_SEATS, dep.available) : 1
  const seats = Math.min(pax, Math.max(1, maxPax))
  const est = { base: p.price * seats, fee: feeFor(p.price * seats, cfg) }
  const shown = quote && step > 1 ? quote : { ...est, total: est.base + est.fee }
  const cover = p.images.find(i => i.is_cover) || p.images[0]

  async function toReview(e) {
    e.preventDefault()
    if (!e.currentTarget.checkValidity()) { e.currentTarget.reportValidity(); return }
    try {
      const q = await api('/public/quote/', { method: 'POST', body: { departure_id: depId, seats } })
      if (q.available < seats) throw new Error(q.available ? `Only ${plural(q.available, 'seat')} available, but ${seats} requested. Overbooking is not allowed.` : 'This date just sold out — pick another date.')
      setQuote(q); setError(''); setStep(2)
    } catch (err) { setError(err.message) }
  }

  async function pay(e) {
    e.preventDefault()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    const fd = Object.fromEntries(new FormData(form))
    // Only a label is sent for the payment — never card numbers (demo payment, nothing is charged).
    const detail = method === 'upi' ? (fd.upi?.trim() || upiApp) : method === 'card' ? `ending ${String(fd.cardNo).replace(/\D/g, '').slice(-4)}` : fd.bank
    setPaying(true)
    await new Promise(r => setTimeout(r, 1200))   // feels like a payment gateway round-trip
    try {
      const b = await api('/public/bookings/', { method: 'POST', body: {
        departure_id: depId, seats, name: lead.name.trim(), phone: lead.phone.trim(), email: lead.email.trim(),
        co_travellers: others.slice(0, seats - 1), payment_method: method, payment_detail: detail } })
      rememberTicket(b.code, b.key)
      navigate(`/ticket/${b.code}` + qs({ new: 1 }), { replace: true })
    } catch (err) {
      setPaying(false)
      setError(`${err.message} No money was charged — please pick another date or fewer seats.`)
      setStep(1)
      api(`/public/packages/${id}/`).then(setP).catch(() => {})
    }
  }

  const side = (
    <aside className="flow-side"><div className="card panel">
      <div className="summary-row"><div className="cover"><CoverImg url={cover?.url} /></div>
        <div><b>{p.title}</b><div className="help" style={{ margin: '2px 0 0' }}>{p.operator.name} {p.operator.verified && <Verified />}</div></div></div>
      <dl className="kv"><dt>Route</dt><dd>{p.from_city} → {p.to_city}</dd><dt>Departure</dt><dd>{dep ? fmtDay(dep.date) : '—'}</dd>
        <dt>Duration</dt><dd>{durationLabel(p.nights)}</dd><dt>Seats</dt><dd>{seats}</dd></dl>
      <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="line"><span>Base fare ({inr(p.price)} × {seats})</span><span>{inr(shown.base)}</span></div>
        <div className="line"><span>Convenience fee</span><span>{inr(shown.fee)}</span></div>
        <div className="line total"><span>Total payable</span><span>{inr(shown.total)}</span></div>
      </div>
    </div></aside>
  )

  let main
  if (step === 1) {
    const st = dep
    const cells = st ? Array.from({ length: st.total }, (_, i) => i < st.booked ? 'booked' : i < st.booked + st.pending ? 'pending' : i < st.booked + st.pending + seats ? 'mine' : 'free') : []
    main = (
      <>
        {error && <div className="form-error" role="alert">{error}</div>}
        {!me && !guestOk && (
          <div className="login-nudge"><span><PIcon name="user" size={18} /> Have an account? Log in to see this booking in My Bookings on any device.</span>
            <span style={{ display: 'flex', gap: 8 }}><Link className="btn btn-sm btn-navy" to={`/account?next=${encodeURIComponent(`/book/${id}` + qs({ dep: depId, pax: seats }))}`}>Log in</Link>
              <button className="btn btn-sm" onClick={() => setGuestOk(true)}>Continue as guest</button></span></div>
        )}
        <div className="card panel">
          <h2><PIcon name="calendar" size={20} /> Select departure</h2>
          {p.departures.some(d => !d.blocked) ? <div className="dates-grid">{p.departures.filter(d => !d.blocked).map(d => {
            const [c, t] = seatText(d)
            return <button key={d.id} className={`date-card ${d.id === depId ? 'sel' : ''}`} disabled={!d.available} onClick={() => { setDepId(d.id); setError('') }}>
              <b>{fmtDay(d.date)}</b><Bar st={d} /><span className={`s ${c}`}>{t}</span></button>
          })}</div> : <p className="help">No upcoming dates are open for this trip.</p>}
        </div>
        <div className="card panel">
          <h2><PIcon name="users" size={20} /> Number of seats</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <div className="stepper"><button type="button" onClick={() => setPax(Math.max(1, seats - 1))} disabled={seats <= 1} aria-label="Fewer seats">−</button><output>{seats}</output>
              <button type="button" onClick={() => setPax(seats + 1)} disabled={!dep || seats >= maxPax} aria-label="More seats">+</button></div>
            {dep && <SeatPill st={dep} />}
          </div>
          {dep && <div style={{ marginTop: 14 }}>
            <div className="seats" aria-hidden="true">{cells.map((c, i) => <span key={i} className={`seat ${c}`} />)}</div>
            <div className="legend"><span><i style={{ background: 'var(--seat-booked)' }} />Booked</span><span><i style={{ background: 'var(--seat-pending)' }} />On hold</span>
              <span><i style={{ background: 'var(--navy)' }} />Your seats</span><span><i style={{ background: '#E3F4E8', border: '1.5px solid var(--seat-free)' }} />Available</span></div>
          </div>}
        </div>
        <form className="card panel" onSubmit={toReview} noValidate>
          <h2><PIcon name="user" size={20} /> Traveller details</h2>
          <div className="form-grid two">
            <div className="full"><label htmlFor="leadName">Lead traveller name</label>
              <input id="leadName" type="text" required maxLength={50} autoComplete="name" placeholder="As on government ID" value={lead.name} onChange={e => setLead({ ...lead, name: e.target.value })} /></div>
            <div><label htmlFor="leadPhone">Mobile number</label>
              <input id="leadPhone" type="tel" required pattern="[6-9][0-9]{9}" inputMode="numeric" maxLength={10} title="10-digit Indian mobile number" autoComplete="tel-national" placeholder="10-digit mobile" value={lead.phone} onChange={e => setLead({ ...lead, phone: e.target.value })} /></div>
            <div><label htmlFor="leadEmail">Email</label>
              <input id="leadEmail" type="email" required autoComplete="email" placeholder="Ticket is sent here" value={lead.email} onChange={e => setLead({ ...lead, email: e.target.value })} /></div>
            {Array.from({ length: seats - 1 }, (_, i) => (
              <div key={i}><label>Traveller {i + 2} name <span style={{ fontWeight: 400 }}>(optional)</span></label>
                <input type="text" maxLength={50} value={others[i] || ''} onChange={e => { const o = [...others]; o[i] = e.target.value; setOthers(o) }} /></div>
            ))}
          </div>
          <div className="help" style={{ marginTop: 10 }}><PIcon name="whatsapp" size={14} /> The operator gets your name and number for pickup coordination only.</div>
          <div style={{ marginTop: 16 }}><button className="btn btn-primary btn-lg btn-block" type="submit" disabled={!dep}>Continue to review <PIcon name="arrow" size={18} /></button></div>
        </form>
      </>
    )
  } else if (step === 2) {
    const co = others.slice(0, seats - 1).filter(x => x?.trim())
    main = (
      <>
        <div className="card panel">
          <h2>Review your booking</h2>
          <dl className="kv">
            <dt>Trip</dt><dd>{p.title}</dd><dt>Operator</dt><dd>{p.operator.name}</dd>
            <dt>Departure</dt><dd>{fmtDay(dep.date)}, {fmtDate(dep.date).split(' ').pop()}</dd>
            <dt>Pickup</dt><dd>{p.pickup_point || `${p.from_city} · time shared after booking`}</dd>
            <dt>Lead traveller</dt><dd>{lead.name} · {lead.phone}<div className="help" style={{ margin: 0 }}>{lead.email}</div></dd>
            {co.length > 0 && <><dt>Co-travellers</dt><dd>{co.join(', ')}</dd></>}
            <dt>Seats</dt><dd>{seats}</dd>
          </dl>
        </div>
        <div className="card panel">
          <h2><PIcon name="rupee" size={20} /> Price breakdown</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="line"><span>Base price ({inr(quote.price)} × {plural(seats, 'seat')})</span><span>{inr(quote.base)}</span></div>
            <div className="line"><span>Convenience fee <span className="help" style={{ display: 'inline' }}>({quote.fee_rate}%, min {inr(quote.fee_min)})</span></span><span>{inr(quote.fee)}</span></div>
            <div className="line total"><span>Total payable</span><span>{inr(quote.total)}</span></div>
          </div>
          <div className="fee-note" style={{ marginTop: 12 }}><PIcon name="info" size={15} /> The operator receives 100% of the base price — PakkaTrip charges them no commission. The convenience fee keeps the platform running and is non-refundable if you cancel.</div>
        </div>
        <div className="card panel">
          <h2><PIcon name="refund" size={20} /> Cancellation policy</h2>
          <PolicyTable policy={cfg.policy} />
          <label className="check" style={{ marginTop: 8 }}><input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} /> I have read the itinerary, inclusions and cancellation policy.</label>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-lg" onClick={() => setStep(1)}><PIcon name="back" size={18} /> Back</button>
          <button className="btn btn-primary btn-lg" style={{ flex: 1 }} disabled={!agree} onClick={() => setStep(3)}>Proceed to pay {inr(quote.total)}</button>
        </div>
      </>
    )
  } else {
    main = (
      <>
        <div className="demo-pay"><PIcon name="info" size={18} /><div><b>Dummy payment.</b> No money is charged. Card details are never sent — only the last 4 digits are kept as a label.</div></div>
        <form className="card panel" onSubmit={pay} noValidate key={method}>
          <h2><PIcon name="lock" size={20} /> Pay {inr(quote.total)}</h2>
          <div className="pay-tabs" role="tablist">
            {[['upi', 'upi', 'UPI'], ['card', 'card', 'Card'], ['netbanking', 'bank', 'Netbanking']].map(([m, ic, t]) => (
              <button key={m} type="button" className={`pay-tab ${method === m ? 'sel' : ''}`} role="tab" aria-selected={method === m} onClick={() => setMethod(m)}><PIcon name={ic} size={22} />{t}</button>
            ))}
          </div>
          {method === 'upi' && <>
            <div className="upi-apps">{['GPay', 'PhonePe', 'Paytm', 'BHIM'].map(a => <button key={a} type="button" className={upiApp === a ? 'sel' : ''} onClick={() => setUpiApp(a)}>{a}</button>)}</div>
            <label htmlFor="upiId">Or enter UPI ID</label><input id="upiId" name="upi" type="text" placeholder="yourname@okbank" pattern="[a-zA-Z0-9._\-]+@[a-zA-Z]+" title="Like name@okhdfc" />
            <div className="help">A collect request would be sent to your UPI app. In this demo, nothing is sent.</div>
          </>}
          {method === 'card' && <>
            <div className="form-grid two">
              <div className="full"><label>Card number</label><input name="cardNo" type="text" inputMode="numeric" placeholder="4111 1111 1111 1111" required pattern="[0-9 ]{15,19}" autoComplete="off" /></div>
              <div><label>Expiry (MM/YY)</label><input name="exp" type="text" placeholder="12/29" required pattern="(0[1-9]|1[0-2])/[0-9]{2}" autoComplete="off" /></div>
              <div><label>CVV</label><input name="cvv" type="password" placeholder="123" required pattern="[0-9]{3}" inputMode="numeric" maxLength={3} autoComplete="off" /></div>
              <div className="full"><label>Name on card</label><input name="cardName" type="text" required autoComplete="off" defaultValue={lead.name} /></div>
            </div>
            <div className="help">Demo only: do not enter a real card. Nothing leaves your browser except the last 4 digits.</div>
          </>}
          {method === 'netbanking' && <>
            <label htmlFor="bank">Choose your bank</label>
            <select id="bank" name="bank" required defaultValue=""><option value="">Select bank…</option>{BANKS.map(b => <option key={b}>{b}</option>)}</select>
            <div className="help">You would be redirected to your bank's login page. In this demo, nothing is redirected.</div>
          </>}
          <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
            <button type="button" className="btn btn-lg" onClick={() => setStep(2)} aria-label="Back"><PIcon name="back" size={18} /></button>
            <button className="btn btn-green btn-lg" style={{ flex: 1 }} type="submit" disabled={paying}><PIcon name="lock" size={18} /> {paying ? 'Processing…' : `Pay ${inr(quote.total)}`}</button>
          </div>
          <div className="secure"><PIcon name="shield" size={14} /> 100% secure payments · Refund protection on every booking</div>
        </form>
      </>
    )
  }

  return (
    <>
      <div className="container">
        <Link className="link" to={`/trips/${p.id}`} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', marginTop: 16 }}><PIcon name="back" size={16} /> Back to trip details</Link>
        <FlowSteps step={step} />
      </div>
      <div className="container flow-layout"><div className="flow-main">{main}</div>{side}</div>
      {paying && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[rgb(11_24_45/.55)]" role="alertdialog" aria-label="Processing payment">
          <div className="card" style={{ padding: 24, textAlign: 'center', maxWidth: 320 }}>
            <div className="spinner" /><p style={{ margin: 0 }}><b>Confirming your seats…</b></p><p className="help">Demo payment — please wait a moment.</p></div>
        </div>
      )}
    </>
  )
}
