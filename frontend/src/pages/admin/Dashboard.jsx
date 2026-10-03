import { Link } from 'react-router-dom'
import { Badge, Icon, LoadError, Loading, StatCard } from '../../components/ui'
import { fmtDate, inr, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function AdminDashboard() {
  const { data: d, error, reload } = useApi('/admin/dashboard/')
  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />

  return (
    <>
      <div className="stats">
        <StatCard icon="ticket" tone="navy" label="Total bookings" value={d.total_bookings.toLocaleString('en-IN')}
          note={`${d.travellers} travellers · ${d.pending} pending · ${d.cancelled} cancelled`} />
        <StatCard icon="wallet" tone="saffron" label="Booking revenue (GMV)" value={inr(d.gmv)} note="Confirmed + completed, paid to operators" />
        <StatCard icon="rupee" tone="green" label="Convenience fee collected" value={inr(d.fees)}
          note={`Your earnings · ${d.fee_rate}% (min ${inr(d.fee_min)}) on online bookings`} />
        <StatCard icon="shield" tone="navy" label="Verified operators" value={`${d.verified_operators} / ${d.total_operators}`} note={`${d.live_packages} live packages`} />
      </div>

      {(d.pending_packages > 0 || d.unverified_operators > 0) && (
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(260px,1fr))]">
          {d.pending_packages > 0 && (
            <div className="card flex items-center gap-3.5 px-[18px] py-4">
              <div className="stat-icon bg-amber-soft text-amber"><Icon name="box" size={20} /></div>
              <div className="flex-1"><b className="font-display text-xl">{d.pending_packages}</b> {d.pending_packages > 1 ? 'packages' : 'package'} waiting for approval</div>
              <Link className="btn btn-sm" to="/admin/packages?f=pending">Review</Link>
            </div>
          )}
          {d.unverified_operators > 0 && (
            <div className="card flex items-center gap-3.5 px-[18px] py-4">
              <div className="stat-icon bg-amber-soft text-amber"><Icon name="alert" size={20} /></div>
              <div className="flex-1"><b className="font-display text-xl">{d.unverified_operators}</b> {d.unverified_operators > 1 ? 'operators' : 'operator'} not yet verified</div>
              <Link className="btn btn-sm" to="/admin/operators?f=unverified">Verify</Link>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Recent bookings</h3><Link className="link" to="/admin/bookings">View all bookings →</Link></div>
        <div className="table-wrap">
          <table className="tbl">
            <thead><tr><th>Booking</th><th>Customer</th><th>Package</th><th>Travel date</th><th className="num">Amount</th><th className="num">Fee</th><th>Status</th></tr></thead>
            <tbody>
              {d.recent.map(b => (
                <tr key={b.id}>
                  <td><span className="mono">{b.id}</span><div className="sub">{fmtDate(b.booked_on)}</div></td>
                  <td>{b.customer}<div className="sub">{plural(b.travellers, 'traveller')}</div></td>
                  <td>{b.pkg_title}<div className="sub">{b.operator_name}</div></td>
                  <td>{fmtDate(b.travel_date)}</td>
                  <td className="num">{inr(b.amount)}</td><td className="num">{inr(b.fee)}</td><td><Badge status={b.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
