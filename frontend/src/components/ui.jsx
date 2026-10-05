import { fmtDate, inr } from '../lib/format'

const ICONS = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c2 .7 3.2 2.4 3.5 5.2" /></>,
  box: <><path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z" /><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9" /></>,
  ticket: <><path d="M3 8a2 2 0 0 0 0 4 2 2 0 0 1 0 4v2h18v-2a2 2 0 0 1 0-4 2 2 0 0 0 0-4V6H3z" /><path d="M14 6v12" strokeDasharray="2 2" /></>,
  seat: <><path d="M6 4h9a2 2 0 0 1 2 2v7H6z" /><path d="M4 13h16v4H4zM6 17v3M18 17v3" /></>,
  wallet: <><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M16 14.5h2" /></>,
  star: <path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" />,
  cog: <><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" /></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  logout: <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  rupee: <path d="M6 4h12M6 9h12M6 4h3.5a5 5 0 0 1 0 10H6l8 7" />,
  shield: <><path d="M12 3 4.5 6v6c0 4.4 3.2 8 7.5 9 4.3-1 7.5-4.6 7.5-9V6z" /><path d="m8.5 12 2.5 2.5 4.5-4.5" /></>,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.01" /></>,
  calendar: <><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  meal: <path d="M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 3c-2 1.5-3 4-3 7h3v11" />,
  bed: <><path d="M3 18V7M3 13h18v5M21 13a3 3 0 0 0-3-3h-7v3" /><circle cx="7" cy="10.5" r="1.8" /></>,
  bus: <><rect x="4" y="3" width="16" height="15" rx="3" /><path d="M4 11h16M8 18v2.5M16 18v2.5" /><circle cx="8" cy="14.5" r="1" /><circle cx="16" cy="14.5" r="1" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  pin: <><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="m21 16-5-5L5 20" /></>,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  left: <path d="M15 6l-6 6 6 6" />,
  right: <path d="M9 6l6 6-6 6" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.5v.01" /></>,
  bank: <><path d="M3 9.5 12 4l9 5.5M4.5 10v8M9.5 10v8M14.5 10v8M19.5 10v8M3 20h18" /></>,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
}

export function Icon({ name, size = 18, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>{ICONS[name]}</svg>
  )
}

export function BrandMark({ size = 36 }) {
  return (
    <div className="grid place-items-center rounded-[10px] bg-saffron flex-none" style={{ width: size, height: size }}>
      <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
    </div>
  )
}
export function Brand({ className = '' }) {
  return <div className={`flex items-center gap-2.5 font-display font-bold text-[19px] ${className}`}><BrandMark /><span>Pakka<b className="text-saffron">Trip</b></span></div>
}

const STATUS = {
  confirmed: ['b-navy', 'Confirmed'], completed: ['b-green', 'Completed'], cancelled: ['b-red', 'Cancelled'], pending: ['b-amber', 'Pending'],
  approved: ['b-green', 'Approved'], rejected: ['b-red', 'Rejected'],
}
export function Badge({ status, pkg }) {
  const [cls, text] = STATUS[status] || ['b-grey', status]
  return <span className={`badge ${cls}`}>{pkg && status === 'pending' ? 'Pending review' : text}</span>
}
/** Verification tiers — same rules as backend/operators/verification.py. */
export const TIERS = [
  ['gold', 'Gold', ['GST', 'PAN + bank', 'Udyam']],
  ['silver', 'Silver', ['PAN + bank', 'Aadhaar']],
  ['bronze', 'Bronze', ['PAN + bank', 'Mobile verified']],
]
export const TierBadge = ({ tier }) => {
  const t = TIERS.find(([id]) => id === tier)
  return t ? <span className={`badge b-${tier}`}>{t[1]}</span> : <span className="badge b-grey">No tier</span>
}
const OP_STATUS = { verified: ['b-green', 'Approved'], pending: ['b-amber', 'Pending review'], rejected: ['b-red', 'Rejected'], suspended: ['b-red', 'Suspended'] }
export const OpStatusBadge = ({ status }) => <span className={`badge ${OP_STATUS[status]?.[0] || 'b-grey'}`}>{OP_STATUS[status]?.[1] || status}</span>

const DEP = { open: ['b-green', 'Open'], fast: ['b-amber', 'Filling fast'], soldout: ['b-red', 'Sold out'], blocked: ['b-grey', 'Blocked'], departed: ['b-navy', 'Departed'] }
export const DepBadge = ({ state }) => <span className={`badge ${DEP[state][0]}`}>{DEP[state][1]}</span>

export const Stars = ({ rating }) => (
  <span className="stars" aria-label={`${rating} out of 5`}>{'★'.repeat(rating)}<span className="off">{'★'.repeat(5 - rating)}</span></span>
)
export const SourceTag = ({ source }) => source === 'offline' ? <span className="tag">Offline</span> : null

export function StatCard({ icon, tone, label, value, note }) {
  const tones = {
    navy: 'bg-navy-soft text-navy-2', saffron: 'bg-saffron-soft text-saffron-dark',
    green: 'bg-leaf-soft text-leaf', amber: 'bg-amber-soft text-amber',
  }
  return (
    <div className="card stat">
      <div className={`stat-icon ${tones[tone]}`}><Icon name={icon} size={21} /></div>
      <div><div className="label">{label}</div><div className="value">{value}</div><div className="note">{note}</div></div>
    </div>
  )
}

export function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="search"><Icon name="search" size={16} />
      <input type="search" value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  )
}

export function Chips({ value, onChange, options }) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {options.map(([v, t]) => <button key={v} className={`chip ${value === v ? 'active' : ''}`} onClick={() => onChange(v)}>{t}</button>)}
    </div>
  )
}

export const EmptyRow = ({ cols, children }) => <tr><td colSpan={cols} className="empty">{children}</td></tr>
export const Loading = () => <div className="card empty">Loading…</div>
export const LoadError = ({ error, retry }) => (
  <div className="card empty">{error.message} <button className="link ml-2" onClick={retry}>Try again</button></div>
)

export function ProgressBar({ st }) {
  const w = n => `${(st.total ? (n / st.total) * 100 : 0).toFixed(2)}%`
  return (
    <div className="progress" title={`${st.booked} booked · ${st.pending} pending · ${st.available} available`}>
      <span className="seg-booked" style={{ width: w(st.booked) }} />
      <span className="seg-pending" style={{ width: w(st.pending) }} />
      <span className="seg-free" style={{ width: w(st.available) }} />
    </div>
  )
}

export function SeatGrid({ st }) {
  return (
    <div className="seats">
      {Array.from({ length: st.total }, (_, i) => {
        const cls = i < st.booked ? 'booked' : i < st.booked + st.pending ? 'pending' : 'free'
        return <span key={i} className={`seat ${cls}`} title={`Seat ${i + 1}: ${cls === 'free' ? 'available' : cls}`} />
      })}
    </div>
  )
}

export const SeatLegend = () => (
  <div className="legend">
    <span><i style={{ background: 'var(--color-seat-booked)' }} />Booked</span>
    <span><i style={{ background: 'var(--color-seat-pending)' }} />Pending (seat on hold)</span>
    <span><i style={{ background: '#E3F4E8', border: '1.5px solid var(--color-seat-free)' }} />Available</span>
    <span><i style={{ background: '#E5E7EB' }} />Blocked</span>
  </div>
)

/** Booking detail shown in the "View" modal — same fields as the prototype. */
export function BookingDetail({ b, forOperator }) {
  return (
    <>
      <dl className="detail">
        <dt>Booking ID</dt><dd className="mono">{b.id}</dd>
        <dt>Status</dt><dd><Badge status={b.status} /></dd>
        <dt>Source</dt><dd>{b.source === 'offline' ? 'Offline (added by operator)' : `Online on PakkaTrip${b.payment ? ` · paid by ${b.payment}` : ''}`}</dd>
        <dt>Customer</dt><dd>{b.customer} · {b.phone}{b.email && <div className="sub">{b.email}</div>}</dd>
        {b.co_travellers?.length > 0 && <><dt>Co-travellers</dt><dd>{b.co_travellers.join(', ')}</dd></>}
        <dt>Package</dt><dd>{b.pkg_title}<div className="sub">{b.route}</div></dd>
        {!forOperator && <><dt>Operator</dt><dd>{b.operator_name}</dd></>}
        <dt>Booked on</dt><dd>{fmtDate(b.booked_on)}</dd>
        <dt>Travel date</dt><dd>{fmtDate(b.travel_date)}</dd>
        <dt>Travellers</dt><dd>{b.travellers}</dd>
        <dt>{forOperator ? 'You receive' : 'Package amount'}</dt><dd>{inr(b.amount)}</dd>
        <dt>Convenience fee</dt><dd>{inr(b.fee)}{forOperator && <span className="sub"> (paid by customer to PakkaTrip)</span>}</dd>
        <dt>Customer paid</dt><dd><b>{inr(b.total)}</b></dd>
      </dl>
      {b.status === 'pending' && <div className="note-box bg-amber-soft text-amber">Seats are on hold until the booking is confirmed or declined.</div>}
      {b.status === 'cancelled' && (
        <div className="note-box bg-danger-soft text-danger">
          Cancelled on {fmtDate(b.cancelled_on)}{b.cancelled_by ? ` by the ${b.cancelled_by}` : ''}. Refund of {inr(b.refund)} marked as initiated.
        </div>
      )}
    </>
  )
}
