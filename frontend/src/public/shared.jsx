/* Building blocks shared by the traveller pages — same markup and class names as the prototype. */
import { ICON_PATHS } from './iconPaths'

export function PIcon({ name, size = 18 }) {
  // Paths are static strings from iconPaths.js (never user data).
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] || '' }} />
}

export const INCLUSIONS = { transport: 'Transport', hotel: 'Hotel stay', camp: 'Camp stay', meals: 'Meals', sightseeing: 'Sightseeing', guide: 'Trip captain', activity: 'Activity' }
export const INC_ICON = { transport: 'bus', hotel: 'bed', camp: 'bed', meals: 'meal', sightseeing: 'camera', guide: 'guide', activity: 'bolt' }
export const MAX_SEATS = 10

export const initials = n => String(n).split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()
export const firstName = n => String(n).split(' ')[0]

export function Stars({ rating }) {
  const r = Math.round(rating)
  return <span className="stars" aria-label={`${Number(rating).toFixed(1)} out of 5`}>{'★'.repeat(r)}<span className="off">{'★'.repeat(5 - r)}</span></span>
}
export const Verified = () => <span className="verified" title="Bharosa badge: documents and licences checked by PakkaTrip"><PIcon name="shield" size={13} />Verified</span>
export function RatingChip({ avg, count }) {
  return count
    ? <span className="rating"><span className="box"><PIcon name="star" size={12} />{avg.toFixed(1)}</span><span className="count">({count} {count === 1 ? 'review' : 'reviews'})</span></span>
    : <span className="pill navy">New on PakkaTrip</span>
}

export function SeatPill({ st, compact }) {
  if (!st) return <span className="pill solid-red">Sold out</span>
  if (st.available <= 3) return <span className="pill red">Only {st.available} {st.available === 1 ? 'seat' : 'seats'} left</span>
  if (st.state === 'fast') return <span className="pill amber">Filling fast · {st.available} left</span>
  return <span className="pill green">{st.available} seats {compact ? 'left' : 'available'}</span>
}
export function seatText(st) {
  if (st.blocked || st.state === 'blocked') return ['grey', 'Not available']
  if (st.state === 'soldout') return ['red', 'Sold out']
  if (st.available <= 3) return ['red', `Only ${st.available} left`]
  if (st.state === 'fast') return ['amber', `${st.available} left · filling fast`]
  return ['green', `${st.available} seats left`]
}
export function Bar({ st }) {
  const w = n => `${(st.total ? (n / st.total) * 100 : 0).toFixed(1)}%`
  return <div className="bar"><span className="seg-booked" style={{ width: w(st.booked) }} /><span className="seg-pending" style={{ width: w(st.pending) }} /><span className="seg-free" style={{ width: w(st.available) }} /></div>
}

/** Package photo, or a plain gradient if a package has none yet. */
export function CoverImg({ url, alt = '' }) {
  return url
    ? <img src={url} alt={alt} className="art" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
    : <div className="art" style={{ position: 'absolute', inset: 0, background: 'linear-gradient(160deg,#8DB8E8,#FFD9A8)' }} />
}

/* Dummy QR — looks like a QR, is not scannable (the booking ID is what staff check). */
export function DummyQR({ text }) {
  const N = 25
  let h = 2166136261
  for (const c of text) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  const bit = (x, y) => { let v = Math.imul(h ^ (x * 73856093) ^ (y * 19349663), 2654435761); v ^= v >>> 15; return (v & 7) < 4 }
  const finder = (x, y, ox, oy) => { const dx = x - ox, dy = y - oy; if (dx < 0 || dy < 0 || dx > 6 || dy > 6) return null
    return dx === 0 || dy === 0 || dx === 6 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4) }
  const rects = []
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    let on = finder(x, y, 0, 0) ?? finder(x, y, N - 7, 0) ?? finder(x, y, 0, N - 7)
    if (on === null) on = (x === 7 || y === 7) && (x < 8 || x > N - 9) && (y < 8 || y > N - 9) ? false : bit(x, y)
    if (on) rects.push(<rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" />)
  }
  return <svg viewBox={`-2 -2 ${N + 4} ${N + 4}`} shapeRendering="crispEdges" role="img" aria-label={`Dummy QR code for ${text}`}>
    <rect x="-2" y="-2" width={N + 4} height={N + 4} fill="#fff" /><g fill="#0B2E59">{rects}</g></svg>
}

/* Tickets booked on this device (guest or signed in): [{ code, key }] — the key lets a guest reopen their ticket. */
const TICKETS_KEY = 'pakkatrip_my_tickets'
export function savedTickets() {
  try { return JSON.parse(localStorage.getItem(TICKETS_KEY) || '[]') } catch { return [] }
}
export function rememberTicket(code, key) {
  if (!code || !key) return
  const list = savedTickets().filter(t => t.code !== code)
  list.unshift({ code, key })
  try { localStorage.setItem(TICKETS_KEY, JSON.stringify(list.slice(0, 50))) } catch { /* storage blocked */ }
}
export const ticketKey = code => savedTickets().find(t => t.code === code)?.key || ''

export const qs = obj => {
  const u = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== '' && v != null) u.set(k, v) })
  const s = u.toString()
  return s ? '?' + s : ''
}
