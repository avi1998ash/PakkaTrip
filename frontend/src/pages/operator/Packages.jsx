import { Link, useNavigate } from 'react-router-dom'
import { Badge, EmptyRow, Icon, LoadError, Loading, Stars } from '../../components/ui'
import { durationLabel, inr } from '../../lib/format'
import { useApi } from '../../lib/useApi'
import { UnverifiedBanner } from './common'

export function CoverThumb({ url }) {
  return url
    ? <img src={url} alt="" className="w-16 h-12 rounded-md object-cover flex-none" />
    : <div className="w-16 h-12 rounded-md bg-page border border-dashed border-line grid place-items-center text-muted flex-none"><Icon name="image" size={16} /></div>
}

export default function OpPackages() {
  const { data, error, reload } = useApi('/operator/packages/')
  const navigate = useNavigate()
  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />

  return (
    <>
      <UnverifiedBanner />
      <div className="toolbar"><div className="flex-1" />
        <Link className="btn btn-primary" to="/operator/packages/new"><Icon name="plus" size={16} /> Add package</Link></div>
      <div className="card"><div className="table-wrap"><table className="tbl">
        <thead><tr><th>Package</th><th>Duration</th><th className="num">Price / person</th><th className="num">Upcoming dates</th><th>Rating</th><th>Status</th><th className="num">Actions</th></tr></thead>
        <tbody>
          {data.length ? data.map(p => (
            <tr key={p.id}>
              <td><div className="flex items-center gap-3"><CoverThumb url={p.cover_url} />
                <div><b>{p.title}</b><div className="sub">{p.from_city} → {p.to_city} · {p.image_count} photos</div></div></div></td>
              <td>{durationLabel(p.nights)}</td>
              <td className="num">{inr(p.price)}</td>
              <td className="num">{p.upcoming_departures}</td>
              <td>{p.reviews ? <><Stars rating={Math.round(p.rating)} /> <span className="sub">{p.rating.toFixed(1)} ({p.reviews})</span></> : <span className="sub">No reviews</span>}</td>
              <td><Badge status={p.status} pkg /></td>
              <td><div className="actions">
                {p.status === 'approved' && <a className="btn btn-sm" href={`/trips/${p.id}`} target="_blank" rel="noreferrer" title="Open the traveller page"><Icon name="eye" size={14} /> View</a>}
                {p.status !== 'rejected' && <button className="btn btn-sm" onClick={() => navigate(`/operator/inventory?pkg=${p.id}`)}>Seats</button>}
                <Link className="btn btn-sm" to={`/operator/packages/${p.id}/edit`}>Edit</Link>
              </div></td>
            </tr>
          )) : <EmptyRow cols={7}>You have no packages yet. Add your first one.</EmptyRow>}
        </tbody>
      </table></div></div>
    </>
  )
}
