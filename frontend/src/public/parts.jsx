import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { addDays, durationLabel, fmtDay, inr, plural, todayISO } from '../lib/format'
import { CoverImg, INC_ICON, INCLUSIONS, MAX_SEATS, PIcon, qs, RatingChip, SeatPill, Verified } from './shared'

const minBookDate = () => addDays(todayISO(), 1)

/** Hero search (home) or compact "modify search" bar (results page). */
export function SearchForm({ init = {}, cities = { from: [], to: [] }, compact, collapsed, id }) {
  const navigate = useNavigate()
  const [v, setV] = useState({ from: init.from || '', to: init.to || '', date: init.date || '', pax: init.pax || 1 })
  const set = (k, x) => setV(s => ({ ...s, [k]: x }))
  const submit = e => {
    e.preventDefault()
    navigate('/search' + qs({ from: v.from.trim(), to: v.to.trim(), date: v.date, pax: v.pax > 1 ? v.pax : '' }))
  }
  const field = (label, icon, input) => <div className="search-field"><label>{label}</label><span className="ic"><PIcon name={icon} size={18} /></span>{input}</div>
  return (
    <form className={compact ? `mod-search ${collapsed ? 'collapsed' : ''}` : 'search-grid'} id={id} onSubmit={submit} autoComplete="off">
      <div style={{ position: 'relative' }}>
        {field('From', 'pin', <input type="text" list="fromList" placeholder="e.g. Delhi" value={v.from} onChange={e => set('from', e.target.value)} />)}
        {!compact && <button className="swap" type="button" aria-label="Swap from and to" onClick={() => setV(s => ({ ...s, from: s.to, to: s.from }))}><PIcon name="swap" size={16} /></button>}
      </div>
      {field('To', 'flag', <input type="text" list="toList" placeholder="e.g. Manali" value={v.to} onChange={e => set('to', e.target.value)} />)}
      {field('Travel date', 'calendar', <input type="date" min={minBookDate()} value={v.date} onChange={e => set('date', e.target.value)} />)}
      {field('Travellers', 'users', (
        <select value={v.pax} onChange={e => set('pax', Number(e.target.value))}>
          {Array.from({ length: MAX_SEATS }, (_, i) => <option key={i} value={i + 1}>{plural(i + 1, 'traveller')}</option>)}
        </select>
      ))}
      <button className={`btn btn-primary ${compact ? '' : 'full'}`} type="submit"><PIcon name="search" size={18} /> {compact ? 'Search' : 'Search trips'}</button>
      <datalist id="fromList">{cities.from.map(c => <option key={c} value={c} />)}</datalist>
      <datalist id="toList">{cities.to.map(c => <option key={c} value={c} />)}</datalist>
    </form>
  )
}

/** Package card — grid (home) or row (search results). */
export function PkgCard({ p, date, pax = 1, row }) {
  const link = `/trips/${p.id}` + qs({ date, pax: pax > 1 ? pax : '' })
  const best = p.best
  return (
    <article className={`card pkg ${row ? 'result' : ''}`}>
      <Link className="cover" to={link} aria-hidden="true" tabIndex={-1}>
        <CoverImg url={p.cover_url} />
        <div className="tl"><span className="chip">{durationLabel(p.nights)}</span></div>
        <div className="tr"><SeatPill st={best} compact /></div>
      </Link>
      <div className="pkg-body">
        <div className="op-line">{p.operator} {p.verified && <Verified />}</div>
        <h3><Link to={link}>{p.title}</Link></h3>
        <div className="route"><PIcon name="pin" size={15} /> {p.from_city} <PIcon name="arrow" size={14} /> {p.to_city}
          <span className="pill grey" style={{ marginLeft: 'auto' }}>{durationLabel(p.nights)}</span></div>
        <div className="incl">{p.inc.map(k => <span key={k}><PIcon name={INC_ICON[k] || 'check'} size={14} />{INCLUSIONS[k] || k}</span>)}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <RatingChip avg={p.rating} count={p.reviews} />
          <span className="next-dep"><PIcon name="calendar" size={14} />
            {best ? (date && best.date === date ? fmtDay(best.date) : `Next: ${fmtDay(best.date)}`) : 'No seats on upcoming dates'}</span>
        </div>
        <div className="pkg-foot">
          <div className="price"><small>Starting from</small><b>{inr(p.price)}</b> <span>/ person</span></div>
          <div className="pkg-actions">
            <Link className="btn btn-sm" to={link}>View Details</Link>
            {best ? <Link className="btn btn-sm btn-primary" to={`/book/${p.id}` + qs({ dep: best.id, pax })}>Book Now</Link>
              : <button className="btn btn-sm btn-primary" disabled>Sold out</button>}
          </div>
        </div>
      </div>
    </article>
  )
}

export const Spinner = ({ text = 'Loading…' }) => <div className="container" style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--muted)' }}>{text}</div>
export const ErrorBox = ({ error }) => (
  <div className="container"><div className="card empty-state" style={{ margin: '30px 0' }}><h3>{error.status === 404 ? 'Not found' : 'Something went wrong'}</h3>
    <p>{error.status === 404 ? "This trip may have been removed or isn't open for booking." : error.message}</p>
    <Link className="btn btn-primary" to="/search">Explore trips</Link></div></div>
)
