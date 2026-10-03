import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { Chips, DepBadge, Icon, LoadError, Loading, ProgressBar, SeatGrid, SeatLegend } from '../../components/ui'
import { api } from '../../lib/api'
import { addDays, fmtDay, inr, plural, todayISO } from '../../lib/format'
import { useApi } from '../../lib/useApi'

function DepartureCard({ d, onAction }) {
  const canBook = !d.departed && !d.blocked && d.available > 0
  return (
    <div className={`card dep-card ${d.blocked ? 'is-blocked' : ''}`}>
      <div className="flex justify-between gap-2.5 items-start">
        <div>
          <h4 className="m-0 font-semibold text-[15px]">{d.package_title}</h4>
          <div className="flex items-center gap-1.5 font-semibold text-navy-2 mt-0.5"><Icon name="calendar" size={15} /> {fmtDay(d.date)}</div>
        </div>
        <DepBadge state={d.state} />
      </div>
      <div className="dep-nums">
        <div><b>{d.total}</b><span>Total</span></div>
        <div className="n-booked"><b>{d.booked}</b><span>Booked</span></div>
        <div className="n-pending"><b>{d.pending}</b><span>Pending</span></div>
        <div className="n-free"><b>{d.available}</b><span>Available</span></div>
      </div>
      <div>
        <div className="flex justify-between text-[12.5px] text-muted mb-1"><span>Occupancy</span><b className="text-ink">{d.occupancy}%</b></div>
        <ProgressBar st={d} />
      </div>
      <SeatGrid st={d} />
      {!d.departed && (
        <div className="flex gap-1.5 flex-wrap">
          <button className="btn btn-sm btn-primary" disabled={!canBook} onClick={() => onAction('book', d)}
            title={canBook ? 'Record a booking taken by phone or walk-in' : d.blocked ? 'Unblock this date first' : 'No seats left'}>
            <Icon name="plus" size={14} /> Add booking</button>
          <button className="btn btn-sm" onClick={() => onAction('edit', d)}>Edit seats</button>
          <button className={`btn btn-sm ${d.blocked ? 'btn-ghost-green' : ''}`} onClick={() => onAction('block', d)}>{d.blocked ? 'Unblock date' : 'Block date'}</button>
          {d.booked + d.pending === 0 && <button className="btn btn-sm btn-ghost-red" onClick={() => onAction('delete', d)}>Delete</button>}
        </div>
      )}
    </div>
  )
}

export default function Inventory() {
  const [params] = useSearchParams()
  const [pkg, setPkg] = useState(params.get('pkg') || 'all')
  const [when, setWhen] = useState('upcoming')
  const { data: deps, error, reload } = useApi(`/operator/departures/?package=${pkg}&when=${when}`)
  const { data: pkgs } = useApi('/operator/packages/')
  const { open, confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const changed = msg => { toast(msg); reload(); refreshCounts() }

  if (error) return <LoadError error={error} retry={reload} />
  const usable = (pkgs || []).filter(p => p.status !== 'rejected')

  const addDeparture = () => {
    if (!usable.length) return toast('Add a package first', true)
    const pre = pkg !== 'all' ? Number(pkg) : usable[0].id
    const seats = usable.find(p => p.id === pre)?.default_seats ?? 20
    open({ title: 'Add departure date', submitLabel: 'Add departure', body: (
      <div className="form-grid">
        <div className="full"><label>Package</label>
          <select name="package_id" required defaultValue={pre}>{usable.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></div>
        <div><label>Departure date</label><input type="date" name="date" required min={todayISO()} defaultValue={addDays(todayISO(), 7)} /></div>
        <div><label>Total seats</label><input type="number" name="total_seats" required min={1} max={80} defaultValue={seats} /></div>
      </div>
    ), onSubmit: async d => {
      await api('/operator/departures/', { method: 'POST', body: { package_id: Number(d.package_id), date: d.date, total_seats: Number(d.total_seats) } })
      changed(`Departure added: ${fmtDay(d.date)}, ${d.total_seats} seats`)
    } })
  }

  const onAction = (kind, d) => {
    if (kind === 'edit') return open({ title: 'Edit seats', body: (
      <div className="form-grid">
        <div className="full"><label>Package</label><div><b>{d.package_title}</b> · {fmtDay(d.date)}</div></div>
        <div className="full"><label>Total seats</label><input type="number" name="total_seats" required min={1} max={80} defaultValue={d.total} /></div>
      </div>
    ), onSubmit: async f => {
      await api(`/operator/departures/${d.id}/`, { method: 'PATCH', body: { total_seats: Number(f.total_seats) } })
      changed(`Seats updated to ${f.total_seats}`)
    } })

    if (kind === 'block') {
      if (d.blocked) return api(`/operator/departures/${d.id}/unblock/`, { method: 'POST' })
        .then(() => changed(`${fmtDay(d.date)} unblocked — open for booking`), e => toast(e.message, true))
      const used = d.booked + d.pending
      return confirm('Block this date?', <>Customers won't be able to book <b>{d.package_title}</b> on <b>{fmtDay(d.date)}</b>.
        {used ? ` The ${plural(used, 'seat')} already booked or on hold are not affected.` : ''}</>, 'Block date', async () => {
        await api(`/operator/departures/${d.id}/block/`, { method: 'POST' })
        changed(`${fmtDay(d.date)} blocked`)
      }, { submitClass: 'btn-navy' })
    }

    if (kind === 'delete') return confirm('Delete departure?', `Remove the ${fmtDay(d.date)} departure? It has no bookings.`, 'Delete', async () => {
      await api(`/operator/departures/${d.id}/`, { method: 'DELETE' })
      changed('Departure deleted')
    })

    if (kind === 'book') {
      const price = usable.find(p => p.id === d.package_id)?.price
      return open({ title: 'Add offline booking', submitLabel: 'Add booking', body: (
        <>
          <p className="mt-0 mb-3.5"><b>{d.package_title}</b> · {fmtDay(d.date)} · <span className={`badge ${d.available ? 'b-green' : 'b-red'}`}>{d.available} of {d.total} seats available</span></p>
          <div className="form-grid">
            <div><label>Customer name</label><input type="text" name="customer" required maxLength={50} /></div>
            <div><label>Mobile</label><input type="tel" name="phone" required pattern="[6-9][0-9]{9}" title="10-digit Indian mobile number" /></div>
            <div><label>Seats requested</label><input type="number" name="travellers" required min={1} max={80} defaultValue={1} /></div>
            <div><label>Payment</label><select name="status"><option value="confirmed">Received — confirm seats</option><option value="pending">Not yet — hold seats</option></select></div>
          </div>
          <div className="help mt-2.5">For bookings taken by phone or WhatsApp.{price ? ` Price ${inr(price)} per person;` : ''} no convenience fee on offline bookings.</div>
        </>
      ), onSubmit: async f => {
        await api(`/operator/departures/${d.id}/bookings/`, { method: 'POST', body: { ...f, travellers: Number(f.travellers) } })
        changed(`${plural(Number(f.travellers), 'seat')} ${f.status === 'pending' ? 'held' : 'booked'} for ${f.customer.trim()}`)
      } })
    }
  }

  return (
    <>
      <div className="toolbar">
        <select className="!w-auto min-w-[200px] max-w-full" value={pkg} onChange={e => setPkg(e.target.value)} aria-label="Filter by package">
          <option value="all">All packages</option>
          {usable.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>
        <Chips value={when} onChange={setWhen} options={[['upcoming', 'Upcoming'], ['past', 'Past']]} />
        <div className="flex-1" />
        <button className="btn btn-primary" onClick={addDeparture}><Icon name="plus" size={16} /> Add departure</button>
      </div>
      <SeatLegend />
      {!deps ? <Loading /> : deps.length ? (
        <div className="dep-grid">{deps.map(d => <DepartureCard key={d.id} d={d} onAction={onAction} />)}</div>
      ) : (
        <div className="card empty">{when === 'upcoming' ? <>No upcoming departures. Click <b>Add departure</b> to open a date for booking.</> : 'No past departures.'}</div>
      )}
    </>
  )
}
