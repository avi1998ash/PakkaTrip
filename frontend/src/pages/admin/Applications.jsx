import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import OperatorReview from '../../components/OperatorReview'
import { Chips, LoadError, Loading } from '../../components/ui'
import { useApi } from '../../lib/useApi'

/** Operators waiting for approval (self sign-ups and admin-added ones), oldest first. */
export default function AdminApplications() {
  const [f, setF] = useState('pending')
  const { data, error, reload } = useApi('/admin/applications/')
  const { refreshCounts } = useOutletContext()
  if (error) return <LoadError error={error} retry={reload} />
  if (!data) return <Loading />
  const rows = data.filter(a => a.status === f)
  const n = s => data.filter(a => a.status === s).length

  return (
    <>
      <div className="toolbar">
        <Chips value={f} onChange={setF} options={[['pending', `Waiting for review (${n('pending')})`], ['rejected', `Sent back (${n('rejected')})`]]} />
        <div className="flex-1" />
        <span className="sub">Approve needs at least Bronze · Gold: GST + PAN + bank + Udyam · Silver: PAN + bank + Aadhaar · Bronze: PAN + bank + phone OTP</span>
      </div>
      {rows.length ? rows.map(a => (
        <div key={a.operator_id} className="card">
          <div className="card-head"><h3>{a.name}</h3></div>
          <div className="p-[18px]"><OperatorReview initial={a} onChanged={() => { refreshCounts(); reload() }} /></div>
        </div>
      )) : <div className="card empty">{f === 'pending' ? 'No applications waiting. 🎉' : 'No applications have been sent back.'}</div>}
    </>
  )
}
