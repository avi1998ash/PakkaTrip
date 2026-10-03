import { useOutletContext } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtDate, inr, plural } from '../lib/format'
import { useFeedback } from './feedback'
import { Badge, BookingDetail, EmptyRow, SourceTag } from './ui'

/** View / confirm / decline / cancel — the same actions on the admin and operator pages. */
export function useBookingActions(role, onChange) {
  const { open, confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const base = role === 'admin' ? '/admin/bookings' : '/operator/bookings'
  const done = msg => { toast(msg); onChange?.(); refreshCounts() }

  return {
    view: async code => {
      try {
        const b = await api(`${base}/${code}/`)
        open({ title: `Booking ${b.id}`, body: <BookingDetail b={b} forOperator={role === 'operator'} /> })
      } catch (e) { toast(e.message, true) }
    },
    confirmBooking: async b => {
      try {
        await api(`${base}/${b.id}/confirm/`, { method: 'POST' })
        done(`Booking ${b.id} confirmed — ${plural(b.travellers, 'seat')} now booked`)
      } catch (e) { toast(e.message, true) }
    },
    cancel: b => {
      const decline = b.status === 'pending' && role === 'operator'
      confirm(decline ? 'Decline booking?' : 'Cancel booking?',
        <>{decline ? 'Decline' : 'Cancel'} <b>{b.id}</b> for {b.customer}? {plural(b.travellers, 'seat')} will be released
          {b.source === 'online' && b.status !== 'pending' ? <>, and a full refund of <b>{inr(b.total)}</b> will be initiated</> : null}.</>,
        decline ? 'Decline booking' : 'Cancel booking',
        async () => {
          await api(`${base}/${b.id}/cancel/`, { method: 'POST' })
          done(`Booking ${b.id} ${decline ? 'declined' : 'cancelled'}`)
        }, { cancelLabel: 'Keep booking' })
    },
  }
}

export function BookingRows({ rows, showOperator, operatorActions, actions, emptyText = 'No bookings match.' }) {
  const cols = showOperator ? 9 : 8
  if (!rows.length) return <EmptyRow cols={cols}>{emptyText}</EmptyRow>
  return rows.map(b => (
    <tr key={b.id}>
      <td><span className="mono">{b.id}</span><SourceTag source={b.source} /><div className="sub">{fmtDate(b.booked_on)}</div></td>
      <td>{b.customer}<div className="sub">{b.phone}</div></td>
      <td>{b.pkg_title}<div className="sub">{showOperator ? b.operator_name : b.route}</div></td>
      <td>{fmtDate(b.travel_date)}</td>
      <td className="num">{b.travellers}</td>
      <td className="num">{inr(b.amount)}</td>
      {showOperator && <td className="num">{inr(b.fee)}</td>}
      <td><Badge status={b.status} /></td>
      <td>
        <div className="actions">
          <button className="btn btn-sm" onClick={() => actions.view(b.id)}>View</button>
          {operatorActions && b.status === 'pending' && <button className="btn btn-sm btn-ghost-green" onClick={() => actions.confirmBooking(b)}>Confirm</button>}
          {(b.status === 'pending' || b.status === 'confirmed') &&
            <button className="btn btn-sm btn-ghost-red" onClick={() => actions.cancel(b)}>{b.status === 'pending' && operatorActions ? 'Decline' : 'Cancel'}</button>}
        </div>
      </td>
    </tr>
  ))
}

export const BOOKING_CHIPS = [['all', 'All'], ['pending', 'Pending'], ['confirmed', 'Confirmed'], ['completed', 'Completed'], ['cancelled', 'Cancelled']]
export const earned = b => b.status === 'confirmed' || b.status === 'completed'
