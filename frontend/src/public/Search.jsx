import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { durationLabel, fmtDay, inr, plural } from '../lib/format'
import { ErrorBox, PkgCard, SearchForm } from './parts'
import { MAX_SEATS, PIcon } from './shared'

const DEFAULTS = { maxPrice: 15000, durations: [], minRating: 0, inc: [], sort: 'popular' }
const FILTER_INC = [['transport', 'Transport'], ['stay', 'Hotel / camp stay'], ['meals', 'Meals'], ['sightseeing', 'Sightseeing'], ['activity', 'Adventure activity']]
const hasInc = (p, k) => (k === 'stay' ? p.inc.includes('hotel') || p.inc.includes('camp') : p.inc.includes(k))
const SORTS = {
  popular: (a, b) => b.popularity - a.popularity,
  priceLow: (a, b) => a.price - b.price,
  priceHigh: (a, b) => b.price - a.price,
  rating: (a, b) => b.rating - a.rating || b.reviews - a.reviews,
  soonest: (a, b) => String(a.best?.date || '9').localeCompare(String(b.best?.date || '9')),
}

export default function Search() {
  const [params] = useSearchParams()
  const from = params.get('from') || '', to = params.get('to') || '', date = params.get('date') || ''
  const pax = Math.max(1, Math.min(MAX_SEATS, Number(params.get('pax')) || 1))
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [cities, setCities] = useState({ from: [], to: [] })
  const [f, setF] = useState(DEFAULTS)
  const [drawer, setDrawer] = useState(false)
  const [showMod, setShowMod] = useState(false)

  useEffect(() => { api('/public/config/').then(c => setCities(c.cities)).catch(() => {}) }, [])
  useEffect(() => {
    document.title = 'Search trips — PakkaTrip'
    setRows(null)
    api('/public/packages/' + `?${new URLSearchParams({ from, to, date, pax })}`).then(setRows, setError)
  }, [from, to, date, pax])

  const filtered = useMemo(() => (rows || [])
    .filter(p => p.price <= f.maxPrice
      && (!f.durations.length || f.durations.includes(Math.min(3, p.nights)))
      && (!f.minRating || (p.reviews && p.rating >= f.minRating))
      && f.inc.every(k => hasInc(p, k)))
    .sort((a, b) => (!a.best - !b.best) || SORTS[f.sort](a, b)), [rows, f])   // sold out always last

  if (error) return <ErrorBox error={error} />
  const title = from || to ? `${from || 'Anywhere'} → ${to || 'Anywhere'}` : 'All trips'
  const count = fn => (rows || []).filter(fn).length
  const toggle = (key, v) => setF(s => ({ ...s, [key]: s[key].includes(v) ? s[key].filter(x => x !== v) : [...s[key], v] }))
  const nActive = f.durations.length + f.inc.length + (f.minRating ? 1 : 0) + (f.maxPrice < 15000 ? 1 : 0)
  const chip = (label, onClick) => <button key={label} onClick={onClick}>{label} <PIcon name="x" size={12} /></button>

  return (
    <>
      <div className="page-top"><div className="container">
        <div className="mod-summary"><div><b>{title}</b><small>{date ? fmtDay(date) : 'Any date'} · {plural(pax, 'traveller')}</small></div>
          <button className="btn btn-sm" onClick={() => setShowMod(m => !m)}>Modify</button></div>
        <div className="mod-search-wrap" style={{ marginTop: 8 }}>
          <SearchForm key={`${from}|${to}|${date}|${pax}`} compact collapsed={!showMod} init={{ from, to, date, pax }} cities={cities} />
        </div>
      </div></div>

      <div className="container results-layout">
        <aside className={`card filters ${drawer ? 'open' : ''}`} aria-label="Filters">
          <div className="drawer-head"><h3>Filters</h3><button className="icon-btn" onClick={() => setDrawer(false)} aria-label="Close filters"><PIcon name="x" size={22} /></button></div>
          <div><h4>Sort by</h4><select value={f.sort} onChange={e => setF({ ...f, sort: e.target.value })}>
            {[['popular', 'Popularity'], ['priceLow', 'Price: low to high'], ['priceHigh', 'Price: high to low'], ['rating', 'Rating'], ['soonest', 'Earliest departure']].map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select></div>
          <div><h4>Price per person</h4>
            <input type="range" min={2000} max={15000} step={500} value={f.maxPrice} onChange={e => setF({ ...f, maxPrice: Number(e.target.value) })} aria-label="Maximum price" />
            <div className="range-vals"><span>₹2,000</span><b>Up to {inr(f.maxPrice)}</b></div></div>
          <div><h4>Duration</h4>{[1, 2, 3].map(n => (
            <label key={n} className="opt"><input type="checkbox" checked={f.durations.includes(n)} onChange={() => toggle('durations', n)} />{durationLabel(n)}{n === 3 ? '+' : ''}
              <span className="n">{count(p => Math.min(3, p.nights) === n)}</span></label>))}</div>
          <div><h4>Operator rating</h4>{[[0, 'Any rating'], [4.5, '4.5★ & above'], [4, '4★ & above'], [3, '3★ & above']].map(([v, t]) => (
            <label key={v} className="opt"><input type="radio" name="minRating" checked={f.minRating === v} onChange={() => setF({ ...f, minRating: v })} />{t}</label>))}</div>
          <div><h4>Inclusions</h4>{FILTER_INC.map(([k, t]) => (
            <label key={k} className="opt"><input type="checkbox" checked={f.inc.includes(k)} onChange={() => toggle('inc', k)} />{t}<span className="n">{count(p => hasInc(p, k))}</span></label>))}</div>
          <button className="link" style={{ alignSelf: 'flex-start' }} onClick={() => setF(DEFAULTS)}>Reset all filters</button>
          <div className="drawer-apply"><button className="btn btn-primary btn-block" onClick={() => setDrawer(false)}>Show {plural(filtered.length, 'trip')}</button></div>
        </aside>

        <div>
          <div className="results-head">
            <div><h1>{rows ? `${plural(filtered.length, 'trip')} found` : 'Searching…'}</h1>
              <div className="help" style={{ margin: 0 }}>{title}{date ? ` · from ${fmtDay(date)}` : ''} · seats for {plural(pax, 'traveller')}</div></div>
            <button className="btn btn-sm filter-btn" onClick={() => setDrawer(true)}><PIcon name="filter" size={16} /> Filters{nActive ? ` (${nActive})` : ''}</button>
          </div>
          {nActive > 0 && (
            <div className="active-filters">
              {f.maxPrice < 15000 && chip(`Under ${inr(f.maxPrice)}`, () => setF({ ...f, maxPrice: 15000 }))}
              {f.durations.map(n => chip(durationLabel(n), () => toggle('durations', n)))}
              {f.minRating > 0 && chip(`${f.minRating}★ & above`, () => setF({ ...f, minRating: 0 }))}
              {f.inc.map(k => chip(FILTER_INC.find(x => x[0] === k)[1], () => toggle('inc', k)))}
            </div>
          )}
          <div className="results-list">
            {!rows ? <div className="card empty-state">Loading trips…</div>
              : filtered.length ? filtered.map(p => <PkgCard key={p.id} p={p} date={date} pax={pax} row />)
                : (
                  <div className="card empty-state"><h3>No trips match</h3>
                    <p>{rows.length ? 'Try removing a filter or raising the price limit.' : 'No operator lists this route yet. Try a nearby city or browse all trips.'}</p>
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: 12 }}>
                      {rows.length > 0 && <button className="btn" onClick={() => setF(DEFAULTS)}>Reset filters</button>}
                      <Link className="btn btn-primary" to="/search">Browse all trips</Link></div>
                  </div>
                )}
          </div>
        </div>
      </div>
    </>
  )
}
