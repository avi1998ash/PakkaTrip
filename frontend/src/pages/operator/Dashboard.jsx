import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookingRows, useBookingActions } from '../../components/bookings'
import { DepBadge, LoadError, Loading, StatCard } from '../../components/ui'
import { UnverifiedBanner } from './common'
import { fmtDay, inr, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

function relativeDays(iso) {
  if (!iso) return ''
  const target = new Date(iso + 'T00:00:00')
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const diffDays = Math.round((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return 'today'
  if (diffDays === 1) return 'tomorrow'
  if (diffDays > 1) return `in ${diffDays} days`
  if (diffDays === -1) return 'yesterday'
  if (diffDays < -1) return `${Math.abs(diffDays)} days ago`
  return ''
}

function DonutChart({ booked = 0, pending = 0, total = 0, occupancy = 0 }) {
  const size = 114
  const strokeWidth = 12
  const radius = (size - strokeWidth) / 2
  const circ = 2 * Math.PI * radius
  const t = total > 0 ? total : 1
  const bookedLen = Math.min(circ, (booked / t) * circ)
  const pendingLen = Math.min(circ - bookedLen, (pending / t) * circ)
  const pct = total > 0 ? (occupancy ?? Math.round(((booked + pending) / total) * 100)) : 0

  return (
    <div className="relative flex-none" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        {/* Background open ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#EDF2F7"
          strokeWidth={strokeWidth}
        />
        {/* Booked arc (Red) */}
        {booked > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#E24B4B"
            strokeWidth={strokeWidth}
            strokeDasharray={`${bookedLen} ${circ - bookedLen}`}
            strokeDashoffset={0}
            strokeLinecap="butt"
          />
        )}
        {/* On hold arc (Amber) */}
        {pending > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#F2A726"
            strokeWidth={strokeWidth}
            strokeDasharray={`${pendingLen} ${circ - pendingLen}`}
            strokeDashoffset={-bookedLen}
            strokeLinecap="butt"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center select-none pointer-events-none">
        <span className="text-[21px] font-bold text-slate-900 leading-none font-display">
          {pct}%
        </span>
        <span className="text-[11px] font-medium text-slate-500 mt-1">
          filled
        </span>
      </div>
    </div>
  )
}

function SeatMapGrid({ total = 20, booked = 0, pending = 0, blocked = false }) {
  const count = Math.max(1, total)
  const seats = Array.from({ length: count }, (_, i) => {
    let type = 'available'
    let label = 'Available'
    if (blocked) {
      type = 'blocked'
      label = 'Blocked'
    } else if (i < booked) {
      type = 'booked'
      label = 'Booked'
    } else if (i < booked + pending) {
      type = 'pending'
      label = 'On hold'
    }
    return { num: i + 1, type, label }
  })

  const colorMap = {
    booked: 'bg-[#E24B4B]',
    pending: 'bg-[#F2A726]',
    available: 'bg-[#DCE4EC]',
    blocked: 'bg-slate-300',
  }

  return (
    <div className="grid grid-cols-10 gap-1.5 sm:gap-2">
      {seats.map(s => (
        <div
          key={s.num}
          title={`Seat ${s.num}: ${s.label}`}
          className={`h-6 sm:h-7 rounded-[6px] transition-transform hover:scale-105 cursor-default ${colorMap[s.type]}`}
        />
      ))}
    </div>
  )
}

export default function OpDashboard() {
  const { data: d, error, reload } = useApi('/operator/dashboard/')
  const actions = useBookingActions('operator', reload)
  const [selectedId, setSelectedId] = useState(null)

  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />

  const nextDepartures = d.next_departures || []
  const selectedDep = (selectedId ? nextDepartures.find(x => x.id === selectedId) : null) || nextDepartures[0]

  return (
    <>
      <UnverifiedBanner />
      <div className="stats">
        <StatCard icon="calendar" tone="navy" label="Upcoming departures" value={d.upcoming_departures} note={`${d.blocked_departures} blocked · ${d.live_packages} live packages`} />
        <StatCard icon="seat" tone="saffron" label="Seats filled (upcoming)" value={`${d.seats_filled} / ${d.capacity}`}
          note={`${d.capacity ? Math.round(d.seats_filled / d.capacity * 100) : 0}% occupancy incl. pending`} />
        <StatCard icon="clock" tone="amber" label="Pending requests" value={d.pending_requests} note={`${d.pending_seats} seats on hold`} />
        <StatCard icon="wallet" tone="green" label="Total earnings" value={inr(d.earnings)} note={`Rating ${d.rating ?? '—'} ★ from ${plural(d.reviews, 'review')}`} />
      </div>

      {/* Redesigned My Trips Card matching Image 1 */}
      <div className="card">
        <div className="card-head">
          <h3>My Trips</h3>
          <Link className="link" to="/operator/inventory">Manage seat inventory →</Link>
        </div>

        {nextDepartures.length ? (
          <div className="p-4 sm:p-5 grid grid-cols-1 lg:grid-cols-[1.1fr_1.35fr] gap-6 items-start">
            {/* Left Column: Departures list */}
            <div className="flex flex-col gap-2">
              {nextDepartures.map(dep => {
                const isSelected = dep.id === selectedDep?.id
                return (
                  <button
                    key={dep.id}
                    type="button"
                    onClick={() => setSelectedId(dep.id)}
                    className={`w-full text-left p-3.5 rounded-xl transition-all relative flex items-center justify-between gap-3 cursor-pointer ${
                      isSelected
                        ? 'bg-[#EEF4FB] border border-[#CDE0F7] shadow-xs'
                        : 'hover:bg-slate-50 border border-transparent'
                    }`}
                  >
                    {isSelected && (
                      <span className="absolute left-0 top-3 bottom-3 w-[4px] bg-navy rounded-r" />
                    )}
                    <div className="min-w-0 pr-2">
                      <div className="font-bold text-slate-800 text-[14.5px] truncate">
                        {dep.package_title}
                      </div>
                      <div className="text-xs text-slate-500 mt-1">
                        {fmtDay(dep.date)} <span className="opacity-60">·</span> {relativeDays(dep.date)}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-none">
                      <DepBadge state={dep.state} />
                      <span className="text-xs font-bold text-slate-700">
                        {dep.available} left
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Right Column: Interactive Details Panel */}
            {selectedDep && (
              <div className="bg-[#FAFBFD] border border-slate-200/90 rounded-2xl p-5 sm:p-6 flex flex-col gap-5 shadow-xs">
                {/* Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="text-[17px] sm:text-[18px] font-bold text-slate-900 leading-snug">
                      {selectedDep.package_title}
                    </h4>
                    <div className="text-xs text-slate-500 mt-1">
                      {fmtDay(selectedDep.date)} <span className="opacity-60">·</span> {relativeDays(selectedDep.date)}
                    </div>
                  </div>
                  <DepBadge state={selectedDep.state} />
                </div>

                {/* Donut Chart & Legend */}
                <div className="flex items-center gap-6 sm:gap-8 pt-1">
                  <DonutChart
                    booked={selectedDep.booked}
                    pending={selectedDep.pending}
                    total={selectedDep.total}
                    occupancy={selectedDep.occupancy}
                  />

                  <div className="flex-1 flex flex-col gap-2.5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2.5 text-slate-600 font-medium">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#E24B4B] flex-none" />
                        Booked
                      </span>
                      <span className="font-bold text-slate-900 tabular-nums text-base">
                        {selectedDep.booked}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2.5 text-slate-600 font-medium">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#F2A726] flex-none" />
                        On hold
                      </span>
                      <span className="font-bold text-slate-900 tabular-nums text-base">
                        {selectedDep.pending}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2.5 text-slate-600 font-medium">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#22C55E] flex-none" />
                        Open
                      </span>
                      <span className="font-bold text-slate-900 tabular-nums text-base">
                        {selectedDep.available}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Seat Map */}
                <div className="pt-2">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2.5">
                    Seat Map
                  </div>
                  <SeatMapGrid
                    total={selectedDep.total}
                    booked={selectedDep.booked}
                    pending={selectedDep.pending}
                    blocked={selectedDep.blocked}
                  />
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="empty">No upcoming departures. Add one in Seat Inventory.</div>
        )}
      </div>

      {/* Latest Bookings Table */}
      <div className="card">
        <div className="card-head">
          <h3>Latest bookings</h3>
          <Link className="link" to="/operator/bookings">All my bookings →</Link>
        </div>
        <div className="table-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Booking</th>
                <th>Customer</th>
                <th>Package</th>
                <th>Travel date</th>
                <th className="num">Pax</th>
                <th className="num">Amount</th>
                <th>Status</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              <BookingRows rows={d.recent} operatorActions actions={actions} emptyText="No bookings yet." />
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
