import { useState } from 'react'
import { BOOKING_CHIPS, BookingRows, earned, useBookingActions } from '../../components/bookings'
import { Chips, LoadError, Loading, SearchBox } from '../../components/ui'
import { inr, plural, sum } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function OpBookings() {
  const [q, setQ] = useState('')
  const [f, setF] = useState('all')
  const { data, error, reload } = useApi('/operator/bookings/')
  const actions = useBookingActions('operator', reload)

  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />

  const needle = q.trim().toLowerCase()
  const rows = data.filter(b => (f === 'all' || b.status === f) &&
    (!needle || [b.id, b.customer, b.phone, b.pkg_title].join(' ').toLowerCase().includes(needle)))
  const act = rows.filter(earned)

  return (
    <>
      <div className="toolbar">
        <SearchBox value={q} onChange={setQ} placeholder="Search booking ID, customer or package" />
        <Chips value={f} onChange={setF} options={BOOKING_CHIPS} />
      </div>
      <div className="card">
        <div className="table-wrap"><table className="tbl">
          <thead><tr><th>Booking</th><th>Customer</th><th>Package</th><th>Travel date</th><th className="num">Pax</th><th className="num">Amount</th><th>Status</th><th className="num">Actions</th></tr></thead>
          <tbody><BookingRows rows={rows} operatorActions actions={actions} /></tbody>
        </table></div>
        {rows.length > 0 && (
          <div className="table-foot">
            <span>{plural(rows.length, 'booking')}</span>
            <span>{sum(act, b => b.travellers)} travellers</span>
            <span>You receive <b>{inr(sum(act, b => b.amount))}</b></span>
          </div>
        )}
      </div>
    </>
  )
}
