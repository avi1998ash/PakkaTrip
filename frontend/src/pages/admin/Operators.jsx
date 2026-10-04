import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import OperatorReview from '../../components/OperatorReview'
import { Chips, EmptyRow, Icon, LoadError, Loading, OpStatusBadge, SearchBox, TierBadge } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate } from '../../lib/format'
import { useApi } from '../../lib/useApi'

function OperatorForm({ o = {} }) {
  const editing = !!o.id
  return (
    <div className="form-grid">
      <div className="full"><label>Business name</label><input type="text" name="name" required maxLength={60} defaultValue={o.name} /></div>
      <div><label>Owner name</label><input type="text" name="owner" required maxLength={50} defaultValue={o.owner} /></div>
      <div><label>City</label><input type="text" name="city" required maxLength={40} defaultValue={o.city} /></div>
      <div><label>Mobile (10 digits)</label><input type="tel" name="phone" required pattern="[6-9][0-9]{9}" title="10-digit Indian mobile number" defaultValue={o.phone} /></div>
      <div><label>Login email</label><input type="email" name="email" required defaultValue={o.email} /></div>
      <div className="full"><label>Login password</label>
        <input type="password" name="password" autoComplete="new-password" required={!editing} minLength={6} maxLength={40}
          placeholder={editing ? 'Leave blank to keep the current password' : 'At least 6 characters'} />
        <div className="help">The operator signs in with this email and password on the partner portal.
          {!editing && ' They start as an application; approve them under Applications once they reach at least Bronze.'}
          {editing && ' Changing the mobile number means it has to be verified by OTP again.'}</div></div>
    </div>
  )
}

export default function AdminOperators() {
  const [params] = useSearchParams()
  const [q, setQ] = useState('')
  const [f, setF] = useState(params.get('f') || 'all')
  const { data, error, reload } = useApi('/admin/operators/')
  const { open, confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const changed = msg => { toast(msg); reload(); refreshCounts() }

  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />

  const needle = q.trim().toLowerCase()
  const rows = data.filter(o => (f === 'all' || (f === 'verified') === o.verified) &&
    (!needle || [o.name, o.owner, o.city, o.phone, o.email].join(' ').toLowerCase().includes(needle)))

  const add = () => open({ title: 'Add operator', body: <OperatorForm />, submitLabel: 'Add operator', onSubmit: async d => {
    const o = await api('/admin/operators/', { method: 'POST', body: d })
    changed(`${o.name} added — they can sign in with ${o.email}`)
  } })
  const edit = o => open({ title: 'Edit operator', body: <OperatorForm o={o} />, onSubmit: async d => {
    await api(`/admin/operators/${o.id}/`, { method: 'PATCH', body: d })
    changed('Operator updated')
  } })
  const setVerified = async (o, verified) => {
    await api(`/admin/operators/${o.id}/verify/`, { method: 'POST', body: { verified } })
    changed(verified ? `${o.name} approved ✓` : `${o.name} moved back to Applications`)
  }
  const toggleVerify = o => o.verified
    ? confirm('Remove approval?', <><b>{o.name}</b> goes back to Applications. New packages can't be approved until they're approved again; live packages stay listed.</>,
      'Remove approval', () => setVerified(o, false))
    : setVerified(o, true).catch(e => toast(e.message, true))
  const review = async o => {
    const v = await api(`/admin/operators/${o.id}/verification/`).catch(e => toast(e.message, true))
    if (v) open({ title: `Verification · ${o.name}`, body: <OperatorReview initial={v} onChanged={() => { reload(); refreshCounts() }} /> })
  }
  const remove = o => confirm('Delete operator?',
    <>Delete <b>{o.name}</b>{o.packages ? ` and their ${o.packages} package${o.packages > 1 ? 's' : ''}` : ''}? They will no longer be able to sign in.
      If they have bookings, they are suspended instead so the booking history stays intact.</>,
    'Delete', async () => {
      const r = await api(`/admin/operators/${o.id}/`, { method: 'DELETE' })
      changed(r.result === 'suspended' ? r.detail : 'Operator deleted')
    })

  return (
    <>
      <div className="toolbar">
        <SearchBox value={q} onChange={setQ} placeholder="Search operator, owner, city or email" />
        <Chips value={f} onChange={setF} options={[['all', 'All'], ['verified', 'Approved'], ['unverified', 'Not approved']]} />
        <div className="flex-1" />
        <button className="btn btn-primary" onClick={add}><Icon name="plus" size={16} /> Add operator</button>
      </div>
      <div className="card"><div className="table-wrap"><table className="tbl">
        <thead><tr><th>Operator</th><th>City</th><th>Login email / phone</th><th className="num">Packages</th><th>Status</th><th>Tier</th><th className="num">Actions</th></tr></thead>
        <tbody>
          {rows.length ? rows.map(o => (
            <tr key={o.id}>
              <td><b>{o.name}</b><div className="sub">{o.owner} · joined {fmtDate(o.joined)}</div></td>
              <td>{o.city}</td>
              <td>{o.email}<div className="sub">{o.phone}</div></td>
              <td className="num">{o.packages}</td>
              <td><OpStatusBadge status={o.status} /></td>
              <td><TierBadge tier={o.tier} /></td>
              <td><div className="actions">
                <button className="btn btn-sm" onClick={() => review(o)}>Review</button>
                {o.verified
                  ? <button className="btn btn-sm" onClick={() => toggleVerify(o)}>Unapprove</button>
                  : o.status === 'pending' && <button className="btn btn-sm btn-ghost-green" onClick={() => toggleVerify(o)}>Approve</button>}
                <button className="btn btn-sm" onClick={() => edit(o)}>Edit</button>
                <button className="btn btn-sm btn-ghost-red" onClick={() => remove(o)}>Delete</button>
              </div></td>
            </tr>
          )) : <EmptyRow cols={7}>No operators match.</EmptyRow>}
        </tbody>
      </table></div></div>
    </>
  )
}
