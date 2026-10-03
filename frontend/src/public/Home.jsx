import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtDate, inr, plural } from '../lib/format'
import { ErrorBox, PkgCard, SearchForm, Spinner } from './parts'
import { initials, PIcon, qs, Stars } from './shared'

export default function Home() {
  const [d, setD] = useState(null)
  const [error, setError] = useState(null)
  const navigate = useNavigate()
  useEffect(() => { document.title = 'PakkaTrip — Book verified trip packages'; api('/public/home/').then(setD, setError) }, [])
  if (error) return <ErrorBox error={error} />
  if (!d) return <Spinner />
  const go = (f, t) => navigate('/search' + qs({ from: f, to: t }))

  return (
    <>
      <section className="hero">
        <div className="container">
          <div className="eyebrow" style={{ color: '#FFC58A' }}>India's trip package marketplace</div>
          <h1>Trip <em>pakka</em>, paisa safe.</h1>
          <p className="lead">Compare weekend trips from verified local operators and book your seat in two minutes — no WhatsApp back-and-forth, no advance to unknown numbers.</p>
          <div className="search-card">
            <SearchForm init={{ pax: 2 }} cities={d.cities} />
            <div className="quick">Popular: {d.routes.slice(0, 4).map(r => <button key={r.from + r.to} type="button" onClick={() => go(r.from, r.to)}>{r.from} → {r.to}</button>)}</div>
          </div>
          <div className="trust-strip">
            <div><PIcon name="shield" size={18} /> {d.stats.verified_operators} verified operators</div>
            <div><PIcon name="ticket" size={18} /> Instant e-ticket</div>
            <div><PIcon name="refund" size={18} /> Refund protection</div>
            <div><PIcon name="rupee" size={18} /> No hidden charges</div>
          </div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 12 }}>
        <div className="container">
          <div className="sec-head"><div><div className="eyebrow">Bharosa first</div><h2>Why PakkaTrip?</h2><p>Everything WhatsApp booking can't give you.</p></div></div>
          <div className="why-grid">
            {[['shield', 'var(--green-soft)', 'var(--green)', 'Verified operators', "Every operator's documents and licences are checked before they get the green Bharosa badge."],
              ['ticket', 'var(--saffron-soft)', 'var(--saffron-dark)', 'Pakka booking', 'Your seat is confirmed the moment you pay. E-ticket with a booking ID — no "seat hai na?" follow-ups.'],
              ['refund', 'var(--navy-soft)', 'var(--navy-2)', 'Refund protection', 'Clear cancellation rules shown before you pay, and full refunds if the operator cancels.'],
              ['rupee', 'var(--amber-soft)', 'var(--amber)', 'Compare & save', 'Same route, many operators — compare price, ratings and inclusions side by side.']].map(([ic, bg, fg, t, x]) => (
              <div key={t} className="card why"><div className="ic" style={{ background: bg, color: fg }}><PIcon name={ic} size={24} /></div><div><h3>{t}</h3><p>{x}</p></div></div>
            ))}
          </div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="sec-head"><div><div className="eyebrow">Handpicked</div><h2>Featured trips</h2><p>Most-booked packages from verified operators.</p></div><Link className="link" to="/search">View all trips →</Link></div>
          <div className="pkg-grid">{d.featured.map(p => <PkgCard key={p.id} p={p} />)}</div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="sec-head"><div><div className="eyebrow">Weekend favourites</div><h2>Popular routes</h2></div></div>
          <div className="routes-grid">{d.routes.map(r => (
            <button key={r.from + r.to} className="route-card" onClick={() => go(r.from, r.to)}>
              <b>{r.from} <PIcon name="arrow" size={15} /> {r.to}</b><span>{plural(r.count, 'package')}</span><em>from {inr(r.min_price)}</em></button>
          ))}</div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="sec-head"><div><div className="eyebrow">WhatsApp vs PakkaTrip</div><h2>Booking a trip, the pakka way</h2></div></div>
          <div className="card compare"><table>
            <thead><tr><th /><th>DM / WhatsApp booking</th><th>PakkaTrip</th></tr></thead>
            <tbody>
              <tr><td>Who is the operator?</td><td>Unknown Instagram page</td><td>Verified, with ratings</td></tr>
              <tr><td>Price</td><td>Different for everyone</td><td>Same listed price, fee shown upfront</td></tr>
              <tr><td>Seat confirmation</td><td>"Pakka hai, bhaiya?"</td><td>Instant e-ticket + booking ID</td></tr>
              <tr><td>If plans change</td><td>Advance usually lost</td><td>Clear refund policy</td></tr>
            </tbody></table></div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="sec-head"><div><div className="eyebrow">How it works</div><h2>Book in three steps</h2></div></div>
          <div className="steps-row">
            <div className="card step-card"><h3>Search & compare</h3><p>Pick your route and date. Compare operators, prices, inclusions and reviews.</p></div>
            <div className="card step-card"><h3>Choose seats & pay</h3><p>See live seat availability. Pay by UPI, card or netbanking.</p></div>
            <div className="card step-card"><h3>Get your e-ticket</h3><p>Booking ID and QR ticket instantly. Show it at the pickup point.</p></div>
          </div>
        </div>
      </section>

      <section className="block" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="stats-band">
            <div><b>{d.stats.trips_run.toLocaleString('en-IN')}+</b><span>trips run by our operators</span></div>
            <div><b>{d.stats.travellers.toLocaleString('en-IN')}</b><span>travellers booked</span></div>
            <div><b>{d.stats.avg_rating ?? '—'} ★</b><span>average trip rating</span></div>
            <div><b>{d.stats.verified_operators}</b><span>verified operators</span></div>
          </div>
        </div>
      </section>

      {d.testimonials.length > 0 && (
        <section className="block" style={{ paddingTop: 0 }}>
          <div className="container">
            <div className="sec-head"><div><div className="eyebrow">Travellers say</div><h2>Real reviews, real trips</h2><p>Only travellers who completed a trip can review it.</p></div></div>
            <div className="testi-grid">{d.testimonials.map((r, i) => (
              <div key={i} className="card testi"><Stars rating={r.rating} /><p>"{r.text}"</p>
                <div className="who"><span className="avatar">{initials(r.customer)}</span><div><b>{r.customer}</b><small>{r.package} · {fmtDate(r.date)}</small></div></div></div>
            ))}</div>
          </div>
        </section>
      )}
    </>
  )
}
