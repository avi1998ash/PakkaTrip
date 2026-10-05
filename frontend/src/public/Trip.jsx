import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Gallery from '../components/Gallery'
import { api } from '../lib/api'
import { durationLabel, fmtDate, fmtDay, inr, plural } from '../lib/format'
import { ErrorBox, Spinner } from './parts'
import { PolicyTable } from './PublicLayout'
import { Bar, CoverImg, initials, MAX_SEATS, PIcon, qs, SeatPill, seatText, Stars, TIER_INFO, TierBadge } from './shared'

export const feeFor = (base, cfg) => Math.max(Number(cfg.fee_min), Math.round(base * Number(cfg.fee_rate) / 100))
const SECTION_LABEL = { meals: 'Meals', accommodation: 'Stay', transport: 'Transport', activities: 'Activities', places: 'Sightseeing', other: 'Also included' }

export default function Trip() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [p, setP] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [error, setError] = useState(null)
  const [depId, setDepId] = useState(null)
  const [pax, setPax] = useState(Math.max(1, Math.min(MAX_SEATS, Number(params.get('pax')) || 1)))

  useEffect(() => {
    Promise.all([api(`/public/packages/${id}/`), api('/public/config/')]).then(([d, c]) => {
      setP(d); setCfg(c)
      document.title = `${d.title} — PakkaTrip`
      const want = params.get('date')
      const ok = d.departures.filter(x => !x.blocked && x.available >= 1)
      setDepId((ok.find(x => !want || x.date >= want) || ok[0])?.id ?? null)
    }, setError)
  }, [id])   // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <ErrorBox error={error} />
  if (!p || !cfg) return <Spinner />

  const dep = p.departures.find(d => d.id === depId)
  const maxPax = dep ? Math.min(MAX_SEATS, dep.available) : 1
  const seats = Math.min(pax, Math.max(1, maxPax))
  const base = p.price * seats, fee = feeFor(base, cfg)
  const fac = p.facilities, op = p.operator
  const nReviews = p.reviews_count
  const book = () => dep && navigate(`/book/${p.id}` + qs({ dep: dep.id, pax: seats }))
  const cover = p.images.find(i => i.is_cover) || p.images[0]
  const join = list => list.join(', ') || '—'

  return (
    <>
      <div className="detail-hero"><CoverImg url={cover?.url} alt="" />
        <div className="container">
          <div className="crumb"><Link to="/">Home</Link> › <Link to={'/search' + qs({ from: p.from_city, to: p.to_city })}>{p.from_city} → {p.to_city}</Link></div>
          <h1>{p.title}</h1>
          <div className="meta"><span><PIcon name="pin" size={15} /> {p.from_city} → {p.to_city}</span><span><PIcon name="clock" size={15} /> {durationLabel(p.nights)}</span>
            {nReviews > 0 && <span><Stars rating={p.rating} /> {p.rating.toFixed(1)} ({nReviews})</span>}
            <span>by <b>{op.name}</b></span> <TierBadge tier={op.tier} /></div>
        </div>
      </div>

      <div className="container detail-layout">
        <div className="detail-main">
          <div className="card panel"><h2>Photos</h2><Gallery images={p.images} /></div>

          <div className="card panel">
            <h2>Trip highlights</h2>
            <div className="chips">{fac.places.map(h => <span key={h}>{h}</span>)}</div>
            <div className="glance">
              <div><span className="gi"><PIcon name="bus" size={18} /></span><div><small>Transport</small>{join(fac.transport)}</div></div>
              <div><span className="gi"><PIcon name="bed" size={18} /></span><div><small>Stay</small>{join(fac.accommodation)}</div></div>
              <div><span className="gi"><PIcon name="meal" size={18} /></span><div><small>Meals</small>{join(fac.meals)}</div></div>
              <div><span className="gi"><PIcon name="pin" size={18} /></span><div><small>Pickup</small>{p.pickup_point || `${p.from_city} · time shared after booking`}</div></div>
            </div>
          </div>

          <div className="card panel" id="dates">
            <h2><PIcon name="calendar" size={20} /> Departure dates</h2>
            <p className="help" style={{ margin: '-6px 0 12px' }}>Live seat availability — tap a date to select it.</p>
            {p.departures.length ? (
              <>
                <div className="dates-grid">{p.departures.map(d => {
                  const [c, t] = seatText(d), off = d.blocked || !d.available
                  return (
                    <button key={d.id} className={`date-card ${d.id === depId ? 'sel' : ''}`} disabled={off} aria-pressed={d.id === depId} onClick={() => setDepId(d.id)}>
                      <b>{fmtDay(d.date)}</b>{!d.blocked && <Bar st={d} />}<span className={`s ${c}`}>{t}</span></button>
                  )
                })}</div>
                <div className="legend"><span><i style={{ background: 'var(--seat-booked)' }} />Booked</span><span><i style={{ background: 'var(--seat-pending)' }} />On hold</span><span><i style={{ background: 'var(--seat-free)' }} />Available</span></div>
              </>
            ) : <p className="help">The operator has not opened any upcoming dates yet. Check back soon.</p>}
          </div>

          <div className="card panel">
            <h2>Day-wise itinerary</h2>
            <ol className="timeline">{p.itinerary.map(d => <li key={d.day}><span className="day">Day<br />{d.day}</span><h4>{d.title}</h4><p>{d.text}</p></li>)}</ol>
          </div>

          <div className="card panel">
            <div className="incl-grid">
              <div><h2 style={{ fontSize: 17, marginBottom: 10 }}>Inclusions</h2><ul className="ilist yes">
                {Object.entries(SECTION_LABEL).filter(([k]) => fac[k]?.length).map(([k, label]) => (
                  <li key={k}><PIcon name="check" size={16} /><span><b>{label}</b> — {fac[k].join(', ')}</span></li>))}</ul></div>
              <div><h2 style={{ fontSize: 17, marginBottom: 10 }}>Exclusions</h2><ul className="ilist no">
                {p.exclusions.map(x => <li key={x}><PIcon name="x" size={16} /><span>{x}</span></li>)}</ul></div>
            </div>
          </div>

          <div className="card panel">
            <h2>About the operator</h2>
            <div className="op-card">
              <div className="op-logo">{initials(op.name)}</div>
              <div style={{ flex: 1, minWidth: 180 }}><h3 style={{ fontSize: 17 }}>{op.name} <TierBadge tier={op.tier} /></h3>
                <div className="help" style={{ margin: '2px 0 0' }}>Based in {op.city} · on PakkaTrip since {fmtDate(op.joined)}</div></div>
              <div className="op-stats">
                <div><b>{op.reviews ? `${op.rating.toFixed(1)}★` : '—'}</b><span>{plural(op.reviews, 'review')}</span></div>
                <div><b>{op.trips_run}+</b><span>trips run</span></div>
                <div><b>{op.live_packages}</b><span>live packages</span></div>
              </div>
              {TIER_INFO[op.tier] && <div className="bharosa"><PIcon name="shield" size={20} /><div><b>{TIER_INFO[op.tier][0]} verified:</b> {TIER_INFO[op.tier][1]}
                <span className="help" style={{ display: 'block', margin: '4px 0 0' }}>Gold: GST + PAN + bank + Udyam · Silver: PAN + bank + Aadhaar · Bronze: PAN + bank + mobile</span></div></div>}
            </div>
          </div>

          <div className="card panel" id="reviews">
            <h2>Reviews</h2>
            {nReviews ? (
              <>
                <div className="rating-summary">
                  <div className="rating-big"><b>{p.rating.toFixed(1)}</b><Stars rating={p.rating} /><div className="help">{plural(nReviews, 'review')}</div></div>
                  <div>{[5, 4, 3, 2, 1].map(n => (
                    <div key={n} className="dist-row"><span>{n}★</span><div className="track"><span style={{ width: `${(p.distribution[n] / nReviews) * 100}%` }} /></div><span>{p.distribution[n]}</span></div>))}</div>
                </div>
                {p.reviews.map((r, i) => (
                  <div key={i} className="review"><div className="top"><div><b>{r.customer}</b> · <Stars rating={r.rating} /></div><span className="help" style={{ margin: 0 }}>{fmtDate(r.date)} · Verified trip</span></div>
                    <p>{r.text}</p>{r.reply && <div className="reply"><b>Reply from {op.name}:</b> {r.reply}</div>}</div>
                ))}
                {nReviews > p.reviews.length && <p className="help">Showing {p.reviews.length} of {nReviews} reviews.</p>}
              </>
            ) : <p className="help">No reviews yet — this package is new on PakkaTrip. Reviews come only from travellers who completed the trip.</p>}
          </div>

          <div className="card panel"><h2><PIcon name="refund" size={20} /> Cancellation policy</h2><PolicyTable policy={p.policy} /></div>
        </div>

        <aside className="card book-box">
          <div className="price"><small>Price per person</small><b>{inr(p.price)}</b></div>
          <div><label htmlFor="depSel">Departure date</label>
            <select id="depSel" value={depId ?? ''} onChange={e => setDepId(Number(e.target.value))}>
              {p.departures.filter(d => !d.blocked).map(d => <option key={d.id} value={d.id} disabled={!d.available}>{fmtDay(d.date)} — {d.available ? `${d.available} seats left` : 'Sold out'}</option>)}
              {!p.departures.some(d => !d.blocked) && <option>No dates available</option>}
            </select>
            {dep && <div style={{ marginTop: 8 }}><SeatPill st={dep} /></div>}</div>
          <div><label>Seats</label>
            <div className="stepper"><button type="button" onClick={() => setPax(Math.max(1, seats - 1))} disabled={seats <= 1} aria-label="Fewer seats">−</button><output>{seats}</output>
              <button type="button" onClick={() => setPax(seats + 1)} disabled={!dep || seats >= maxPax} aria-label="More seats">+</button></div>
            {dep && seats >= dep.available && <div className="help" style={{ color: 'var(--red)' }}>Only {plural(dep.available, 'seat')} left on this date.</div>}</div>
          <div>
            <div className="line"><span>{inr(p.price)} × {plural(seats, 'seat')}</span><span>{inr(base)}</span></div>
            <div className="line"><span>Convenience fee</span><span>{inr(fee)}</span></div>
            <div className="line total" style={{ marginTop: 8 }}><span>Total</span><span>{inr(base + fee)}</span></div>
          </div>
          <button className="btn btn-primary btn-lg btn-block" disabled={!dep} onClick={book}>{dep ? 'Book Now' : 'Sold out'}</button>
          <div className="assure"><div><PIcon name="check" size={15} /> Instant pakka confirmation</div><div><PIcon name="check" size={15} /> Pay the operator's listed price — no haggling</div><div><PIcon name="check" size={15} /> Free cancellation 7+ days before departure</div></div>
        </aside>
      </div>
      <div className="sticky-cta">
        <div><small>{dep ? `${fmtDay(dep.date)} · ${plural(seats, 'seat')}` : 'No dates available'}</small><b>{inr(p.price)}</b> <small style={{ display: 'inline' }}>/ person</small></div>
        <button className="btn btn-primary" disabled={!dep} onClick={book}>Book Now</button>
      </div>
    </>
  )
}
