import { Link } from 'react-router-dom'
import { BookingRows, useBookingActions } from '../../components/bookings'
import { DepBadge, LoadError, Loading, ProgressBar, StatCard } from '../../components/ui'
import { UnverifiedBanner } from './common'
import { fmtDay, inr, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function OpDashboard() {
  const { data: d, error, reload } = useApi('/operator/dashboard/')
  const actions = useBookingActions('operator', reload)
  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />

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
      <div className="card">
        <div className="card-head"><h3>Next departures</h3><Link className="link" to="/operator/inventory">Manage seat inventory →</Link></div>
        {d.next_departures.length ? d.next_departures.map(dep => (
          <div key={dep.id} className="mini-dep">
            <div><b>{dep.package_title}</b> <span className="sub">· {fmtDay(dep.date)}</span></div>
            <div><DepBadge state={dep.state} /> <span className="sub">{dep.available} left</span></div>
            <ProgressBar st={dep} />
          </div>
        )) : <div className="empty">No upcoming departures. Add one in Seat Inventory.</div>}
      </div>
      <div className="card">
        <div className="card-head"><h3>Latest bookings</h3><Link className="link" to="/operator/bookings">All my bookings →</Link></div>
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Booking</th><th>Customer</th><th>Package</th><th>Travel date</th><th className="num">Pax</th><th className="num">Amount</th><th>Status</th><th className="num">Actions</th></tr></thead>
          <tbody><BookingRows rows={d.recent} operatorActions actions={actions} emptyText="No bookings yet." /></tbody>
        </table></div>
      </div>
    </>
  )
}
