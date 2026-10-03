import { EmptyRow, LoadError, Loading, StatCard } from '../../components/ui'
import { inr, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function OpEarnings() {
  const { data: d, error, reload } = useApi('/operator/earnings/')
  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />

  return (
    <>
      <div className="stats">
        <StatCard icon="wallet" tone="green" label="Earned (trips completed)" value={inr(d.earned)} note={plural(d.earned_count, 'booking')} />
        <StatCard icon="calendar" tone="navy" label="Upcoming (confirmed)" value={inr(d.upcoming)} note="Paid out after each trip" />
        <StatCard icon="clock" tone="amber" label="Awaiting confirmation" value={inr(d.pending)} note={plural(d.pending_count, 'pending booking')} />
        <StatCard icon="rupee" tone="saffron" label="Commission paid" value="₹0" note="PakkaTrip takes no commission from operators" />
      </div>
      <div className="card">
        <div className="card-head"><h3>Earnings by package</h3>
          <span className="sub">{plural(d.cancelled_count, 'cancelled booking')} ({inr(d.cancelled_amount)}) not counted</span></div>
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Package</th><th className="num">Bookings</th><th className="num">Travellers</th><th className="num">Earned</th><th className="num">Upcoming</th><th className="num">Total</th></tr></thead>
          <tbody>
            {d.by_package.length ? d.by_package.map(r => (
              <tr key={r.title}>
                <td><b>{r.title}</b><div className="sub">{inr(r.price)} / person</div></td>
                <td className="num">{r.trips}</td><td className="num">{r.pax}</td>
                <td className="num">{inr(r.done)}</td><td className="num">{inr(r.up)}</td><td className="num"><b>{inr(r.done + r.up)}</b></td>
              </tr>
            )) : <EmptyRow cols={6}>No earnings yet.</EmptyRow>}
          </tbody>
        </table></div>
        <div className="table-foot"><span>Customers pay PakkaTrip's convenience fee separately — it is never deducted from your amount.</span></div>
      </div>
    </>
  )
}
