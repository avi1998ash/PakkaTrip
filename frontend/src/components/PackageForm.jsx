/** Package fields — shared by the admin (with operator picker) and the operator (own packages only). */
export default function PackageForm({ p = {}, operators }) {
  return (
    <>
      <div className="form-grid">
        <div className="full"><label>Package title</label><input type="text" name="title" required maxLength={70} placeholder="e.g. Manali Weekend Escape" defaultValue={p.title} /></div>
        {operators && (
          <div className="full"><label>Operator</label>
            <select name="operator_id" required defaultValue={p.operator_id || ''}>
              <option value="">Choose operator…</option>
              {operators.map(o => <option key={o.id} value={o.id}>{o.name}{o.verified ? '' : ' (unverified)'}</option>)}
            </select></div>
        )}
        <div><label>From</label><input type="text" name="from_city" required maxLength={40} placeholder="Delhi" defaultValue={p.from_city} /></div>
        <div><label>To</label><input type="text" name="to_city" required maxLength={40} placeholder="Manali" defaultValue={p.to_city} /></div>
        <div><label>Nights</label><input type="number" name="nights" required min={0} max={15} defaultValue={p.nights ?? 1} /></div>
        <div><label>Price per person (₹)</label><input type="number" name="price" required min={1} step={1} defaultValue={p.price ?? ''} /></div>
        <div className="full"><label>Default seats per departure</label><input type="number" name="default_seats" required min={1} max={80} defaultValue={p.default_seats ?? 20} />
          <div className="help">Pre-filled when you add a new departure date. Each date can still have its own seat count.</div></div>
      </div>
      {!p.id && <div className="note-box bg-amber-soft text-amber">New packages start as <b>Pending review</b> and go live once PakkaTrip approves them.</div>}
    </>
  )
}

export const packageBody = d => ({ ...d, nights: Number(d.nights), price: Number(d.price), default_seats: Number(d.default_seats),
  ...(d.operator_id ? { operator_id: Number(d.operator_id) } : {}) })
