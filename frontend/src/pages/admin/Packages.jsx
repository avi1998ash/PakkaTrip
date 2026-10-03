import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { FacilitiesView } from '../../components/Facilities'
import Gallery from '../../components/Gallery'
import PackageForm, { packageBody } from '../../components/PackageForm'
import { CoverThumb } from '../operator/Packages'
import { Badge, Chips, EmptyRow, Icon, LoadError, Loading, SearchBox } from '../../components/ui'
import { api } from '../../lib/api'
import { durationLabel, inr } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function AdminPackages() {
  const [params] = useSearchParams()
  const [q, setQ] = useState('')
  const [f, setF] = useState(params.get('f') || 'all')
  const { data, error, reload } = useApi('/admin/packages/')
  const { open, confirm, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  const changed = msg => { toast(msg); reload(); refreshCounts() }

  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />

  const needle = q.trim().toLowerCase()
  const rows = data.filter(p => (f === 'all' || p.status === f) &&
    (!needle || [p.title, p.from_city, p.to_city, p.operator_name].join(' ').toLowerCase().includes(needle)))

  const withOperators = async (title, p, submitLabel, onSave) => {
    try {
      const operators = await api('/admin/operators/')
      open({ title, body: <PackageForm p={p} operators={operators} />, submitLabel, onSubmit: d => onSave(packageBody(d)) })
    } catch (e) { toast(e.message, true) }
  }
  const add = () => withOperators('Add package', {}, 'Add package', async body => {
    await api('/admin/packages/', { method: 'POST', body })
    changed('Package added — pending review')
  })
  const edit = p => withOperators('Edit package', p, 'Save', async body => {
    await api(`/admin/packages/${p.id}/`, { method: 'PATCH', body })
    changed('Package updated')
  })
  const act = async (p, action, msg) => {
    try { await api(`/admin/packages/${p.id}/${action}/`, { method: 'POST' }); changed(msg) } catch (e) { toast(e.message, true) }
  }
  const reject = p => confirm('Reject package?', <>Reject <b>{p.title}</b>? It won't be shown to customers.</>, 'Reject', () => act(p, 'reject', 'Package rejected'))
  const review = async p => {
    try {
      const d = await api(`/admin/packages/${p.id}/`)
      open({
        title: `Review: ${d.title}`,
        submitLabel: 'Approve package', submitClass: 'btn-primary', cancelLabel: 'Close',
        onSubmit: d.status === 'approved' ? undefined : async () => {
          await api(`/admin/packages/${p.id}/approve/`, { method: 'POST' })
          changed(`"${d.title}" is now live`)
        },
        body: (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13.5px]">
              <span><b>{d.operator_name}</b> {!d.operator_verified && <span className="badge b-amber">Unverified</span>}</span>
              <span>{d.from_city} → {d.to_city}</span><span>{durationLabel(d.nights)}</span><span><b>{inr(d.price)}</b> / person</span>
              <Badge status={d.status} pkg />
            </div>
            <div><div className="font-semibold text-[13.5px] mb-1.5">Photos ({d.images.length})</div><Gallery images={d.images} small /></div>
            <div><div className="font-semibold text-[13.5px] mb-2">Facilities & inclusions</div><FacilitiesView facilities={d.facilities} compact /></div>
            {d.images.length < 4 && <div className="note-box !mt-0 bg-amber-soft text-amber">This package has fewer than 4 photos.</div>}
          </div>
        ),
      })
    } catch (e) { toast(e.message, true) }
  }
  const remove = p => confirm('Delete package?', <>Delete <b>{p.title}</b> and its departure dates? Existing bookings are kept.</>, 'Delete', async () => {
    await api(`/admin/packages/${p.id}/`, { method: 'DELETE' })
    changed('Package deleted')
  })

  return (
    <>
      <div className="toolbar">
        <SearchBox value={q} onChange={setQ} placeholder="Search package, route or operator" />
        <Chips value={f} onChange={setF} options={[['all', 'All'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected']]} />
        <div className="flex-1" />
        <button className="btn btn-primary" onClick={add}><Icon name="plus" size={16} /> Add package</button>
      </div>
      <div className="card"><div className="table-wrap"><table className="tbl">
        <thead><tr><th>Package</th><th>Operator</th><th>Duration</th><th className="num">Price / person</th><th className="num">Upcoming departures</th><th>Status</th><th className="num">Actions</th></tr></thead>
        <tbody>
          {rows.length ? rows.map(p => (
            <tr key={p.id}>
              <td><div className="flex items-center gap-3"><CoverThumb url={p.cover_url} /><div><b>{p.title}</b><div className="sub">{p.from_city} → {p.to_city}</div></div></div></td>
              <td>{p.operator_name}{!p.operator_verified && <> <span className="badge b-amber">Unverified</span></>}</td>
              <td>{durationLabel(p.nights)}</td>
              <td className="num">{inr(p.price)}</td>
              <td className="num">{p.upcoming_departures}</td>
              <td><Badge status={p.status} pkg /></td>
              <td><div className="actions">
                <button className="btn btn-sm" onClick={() => review(p)}><Icon name="eye" size={14} /> Review</button>
                {p.status !== 'approved' && <button className="btn btn-sm btn-ghost-green" onClick={() => act(p, 'approve', `"${p.title}" is now live`)}>Approve</button>}
                {p.status === 'pending' && <button className="btn btn-sm btn-ghost-red" onClick={() => reject(p)}>Reject</button>}
                {p.status === 'approved' && <button className="btn btn-sm" onClick={() => act(p, 'unlist', `"${p.title}" moved back to review`)}>Unlist</button>}
                <button className="btn btn-sm" onClick={() => edit(p)}>Edit</button>
                <button className="btn btn-sm btn-ghost-red" onClick={() => remove(p)}>Delete</button>
              </div></td>
            </tr>
          )) : <EmptyRow cols={7}>No packages match.</EmptyRow>}
        </tbody>
      </table></div></div>
    </>
  )
}
