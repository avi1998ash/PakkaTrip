import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { durationLabel, fmtDate, fmtDay, inr, plural } from '../lib/format'
import { ErrorBox, Spinner } from './parts'
import { PolicyTable } from './PublicLayout'
import { Bar, CoverImg, MAX_SEATS, PIcon, qs, rememberTicket, SeatPill, seatText, TierBadge } from './shared'
import { feeFor } from './Trip'

const STEPS = ['Travellers', 'Review', 'Payment', 'Confirmed']
export const FlowSteps = ({ step }) => (
  <div className="flow-steps">{STEPS.map((t, i) => <div key={t} data-n={i + 1} className={i + 1 < step ? 'done' : i + 1 === step ? 'now' : ''}>{t}</div>)}</div>
)
const holdTime = co => new Date(co.hold_expires_at).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })

let razorpayScript = null
function loadRazorpay() {
  razorpayScript ??= new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve(window.Razorpay)
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = () => resolve(window.Razorpay)
    s.onerror = () => { razorpayScript = null; reject(new Error("Couldn't load Razorpay. Check your internet connection and try again.")) }
    document.body.appendChild(s)
  })
  return razorpayScript
}

let cashfreeScript = null
function loadCashfree() {
  cashfreeScript ??= new Promise((resolve, reject) => {
    if (window.Cashfree) return resolve(window.Cashfree)
    const s = document.createElement('script')
    s.src = 'https://sdk.cashfree.com/js/v3/cashfree.js'
    s.onload = () => resolve(window.Cashfree)
    s.onerror = () => { cashfreeScript = null; reject(new Error("Couldn't load Cashfree SDK. Check your internet connection and try again.")) }
    document.body.appendChild(s)
  })
  return cashfreeScript
}

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
  const [error, setError] = useState('')
  const [checkout, setCheckout] = useState(null)   // held booking + gateway order from the server
  const [paying, setPaying] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [payNote, setPayNote] = useState('')
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

  function backToStart(message) {
    setCheckout(null); setPaying(false); setVerifying(false); setPayNote('')
    setError(message)
    setStep(1)
    api(`/public/packages/${id}/`).then(setP).catch(() => {})
  }

  // Step 1 of payment: hold seats on the server and get a gateway order (Cashfree or Razorpay).
  async function pay() {
    setPayNote(''); setPaying(true)
    let co = checkout
    try {
      if (!co || new Date(co.hold_expires_at) <= new Date()) {
        co = await api('/public/bookings/', { method: 'POST', body: {
          departure_id: depId, seats, name: lead.name.trim(), phone: lead.phone.trim(), email: lead.email.trim(),
          co_travellers: others.slice(0, seats - 1) } })
        setCheckout(co)
      }

      if (co.gateway === 'cashfree') {
        const Cashfree = await loadCashfree()
        const cf = Cashfree({ mode: co.cashfree.environment === 'production' ? 'production' : 'sandbox' })
        cf.checkout({
          paymentSessionId: co.cashfree.payment_session_id,
          redirectTarget: '_modal'
        }).then(result => {
          if (result?.error) {
            setPaying(false)
            setPayNote(`${result.error.message || 'Payment not completed.'} You can try again or use another method.`)
          } else {
            verifyCashfree(co, result)
          }
        }).catch(err => {
          setPaying(false)
          setPayNote(err.message || 'Cashfree checkout error.')
        })
        return
      }

      const Razorpay = await loadRazorpay()
      const rzp = new Razorpay({
        key: co.razorpay.key, order_id: co.razorpay.order_id, amount: co.razorpay.amount, currency: co.razorpay.currency,
        name: co.razorpay.name, description: co.razorpay.description, prefill: co.razorpay.prefill, notes: co.razorpay.notes,
        theme: { color: '#0B2E59' },
        handler: resp => verify(co, resp),
        modal: { ondismiss: () => { setPaying(false); setPayNote(`Payment not completed. Your ${plural(seats, 'seat')} stay on hold until ${holdTime(co)}.`) } },
      })
      rzp.on('payment.failed', resp => setPayNote(`${resp.error?.description || 'Payment failed.'} You can try again or use another method.`))
      rzp.open()
    } catch (err) {
      if (co) { setPaying(false); setPayNote(err.message); return }
      backToStart(`${err.message} No money was charged — please pick another date or fewer seats.`)
    }
  }

  // Step 2: Cashfree payment callback verification
  async function verifyCashfree(co, result) {
    setPaying(false); setVerifying(true)
    try {
      const b = await api(`/public/bookings/${co.code}/pay/verify/`, {
        method: 'POST',
        body: {
          key: co.key,
          gateway: 'cashfree',
          cashfree_order_id: co.cashfree.order_id,
          order_id: co.cashfree.order_id,
          payment_session_id: co.cashfree.payment_session_id,
          signature: result?.paymentDetails?.signature || '',
        }
      })
      rememberTicket(b.code, b.key)
      navigate(`/ticket/${b.code}` + qs({ new: 1 }), { replace: true })
    } catch (err) {
      if (err.status === 409) backToStart(err.message)
      else { setVerifying(false); setPayNote(err.message) }
    }
  }

  // Step 2: Razorpay checkout success callback
  async function verify(co, resp) {
    setPaying(false); setVerifying(true)
    try {
      const b = await api(`/public/bookings/${co.code}/pay/verify/`, { method: 'POST', body: { key: co.key, ...resp } })
      rememberTicket(b.code, b.key)
      navigate(`/ticket/${b.code}` + qs({ new: 1 }), { replace: true })
    } catch (err) {
      if (err.status === 409) backToStart(err.message)
      else { setVerifying(false); setPayNote(err.message) }
    }
  }

  // Leaving the payment step: give the held seats back right away instead of waiting for the hold to lapse.
  function leavePayment() {
    if (checkout) api(`/public/bookings/${checkout.code}/pay/abandon/`, { method: 'POST', body: { key: checkout.key } }).catch(() => {})
    setCheckout(null); setPayNote(''); setStep(2)
  }

  const side = (
    <aside className="flow-side"><div className="card panel">
      <div className="summary-row"><div className="cover"><CoverImg url={cover?.url} /></div>
        <div><b>{p.title}</b><div className="help" style={{ margin: '2px 0 0' }}>{p.operator.name} <TierBadge tier={p.operator.tier} /></div></div></div>
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
    const isCashfree = checkout ? checkout.gateway === 'cashfree' : (cfg.active_payment_gateway || 'cashfree') === 'cashfree'
    const gwName = isCashfree ? 'Cashfree' : 'Razorpay'

    main = (
      <>
        {cfg.payments_test_mode && (
          <div className="demo-pay"><PIcon name="info" size={18} /><div>
            {isCashfree ? (
              <><b>Cashfree test mode (Sandbox).</b> No real money moves. Pay with test UPI <b>success@cashfree</b> (or <b>failure@cashfree</b> to simulate failure), or any test card / netbanking.</>
            ) : (
              <><b>Razorpay test mode.</b> No real money moves. Pay with UPI ID <b>success@razorpay</b> (or <b>failure@razorpay</b> to see a failed payment), or a Razorpay test card.</>
            )}
          </div></div>
        )}
        <div className="card panel">
          <h2><PIcon name="lock" size={20} /> Pay {inr(quote.total)}</h2>
          <p style={{ margin: '0 0 12px' }}>Pay securely with UPI, card, netbanking or wallet on {gwName}. Your {plural(seats, 'seat')} {checkout ? <>are held until <b>{holdTime(checkout)}</b></> : 'will be held for you while you pay'}.</p>
          <div className="pay-tabs" aria-hidden="true">
            {[['upi', 'UPI'], ['card', 'Cards'], ['bank', 'Netbanking']].map(([ic, t]) => <div key={t} className="pay-tab"><PIcon name={ic} size={22} />{t}</div>)}
          </div>
          {payNote && <div className="form-error" role="alert">{payNote}</div>}
          <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
            <button type="button" className="btn btn-lg" onClick={leavePayment} disabled={paying} aria-label="Back"><PIcon name="back" size={18} /></button>
            <button className="btn btn-green btn-lg" style={{ flex: 1 }} type="button" onClick={pay} disabled={paying}><PIcon name="lock" size={18} /> {paying ? `Opening ${gwName}…` : payNote ? `Try again · ${inr(quote.total)}` : `Pay ${inr(quote.total)}`}</button>
          </div>
          <div className="secure"><PIcon name="shield" size={14} /> Payments by {gwName} · PakkaTrip never sees your card or bank details</div>
        </div>
      </>
    )
  }

  const isCashfree = checkout ? checkout.gateway === 'cashfree' : (cfg.active_payment_gateway || 'cashfree') === 'cashfree'
  const gwName = isCashfree ? 'Cashfree' : 'Razorpay'

  return (
    <>
      <div className="container">
        <Link className="link" to={`/trips/${p.id}`} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', marginTop: 16 }}><PIcon name="back" size={16} /> Back to trip details</Link>
        <FlowSteps step={step} />
      </div>
      <div className="container flow-layout"><div className="flow-main">{main}</div>{side}</div>
      {verifying && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[rgb(11_24_45/.55)]" role="alertdialog" aria-label="Confirming payment">
          <div className="card" style={{ padding: 24, textAlign: 'center', maxWidth: 320 }}>
            <div className="spinner" /><p style={{ margin: 0 }}><b>Confirming your seats…</b></p><p className="help">Checking your payment with {gwName}. Please don't close this page.</p></div>
        </div>
      )}
    </>
  )
}
