import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, apiBlob } from '../lib/api'
import { useFeedback } from './feedback'
import { Icon, OpStatusBadge, TierBadge } from './ui'

const DOC_BADGE = { pending: ['b-amber', 'Waiting for review'], verified: ['b-green', 'Verified'], rejected: ['b-red', 'Sent back'] }
const Status = ({ status, none = 'Not added' }) => status
  ? <span className={`badge ${DOC_BADGE[status][0]}`}>{DOC_BADGE[status][1]}</span>
  : <span className="badge b-grey">{none}</span>
const noEnter = e => { if (e.key === 'Enter') e.preventDefault() }   // the panel can sit inside the modal's form

/** One document with Verify / Send back. */
function DocRow({ v, kind, title, children, onChange }) {
  const { toast } = useFeedback()
  const doc = v.documents[kind]
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const act = async (action, body) => {
    setBusy(true)
    try {
      onChange(await api(`/admin/operators/${v.operator_id}/documents/${kind}/${action}/`, { method: 'POST', body }))
      toast(action === 'verify' ? `${title} verified` : `${title} sent back`); setRejecting(false); setReason('')
    } catch (err) { toast(err.message, true) } finally { setBusy(false) }
  }
  return (
    <div className="py-3 border-t border-line">
      <div className="flex items-start gap-2 flex-wrap">
        <div className="flex-1 min-w-[180px]"><b>{title}</b>{doc && <div className="mono text-[13px]">{doc.number}</div>}{children}
          {doc?.status === 'rejected' && <div className="sub" style={{ color: 'var(--color-danger)' }}>Sent back: {doc.rejection_reason}</div>}</div>
        <Status status={doc?.status} />
      </div>
      {doc && doc.status !== 'rejected' && !rejecting && (
        <div className="flex gap-2 mt-2">
          {doc.status !== 'verified' && <button className="btn btn-sm btn-ghost-green" type="button" disabled={busy} onClick={() => act('verify')}>Verify</button>}
          <button className="btn btn-sm btn-ghost-red" type="button" disabled={busy} onClick={() => setRejecting(true)}>Send back</button>
        </div>
      )}
      {rejecting && (
        <div className="flex gap-2 mt-2">
          <input aria-label={`Reason for sending back ${title}`} placeholder="What should the operator fix?" maxLength={200} value={reason} onKeyDown={noEnter} onChange={e => setReason(e.target.value)} />
          <button className="btn btn-sm btn-danger flex-none" type="button" disabled={busy || reason.trim().length < 5} onClick={() => act('reject', { reason })}>Send back</button>
          <button className="btn btn-sm flex-none" type="button" onClick={() => setRejecting(false)}>Cancel</button>
        </div>
      )}
    </div>
  )
}

/** Everything an admin needs to review one operator: checks, documents, tier, approve / reject. */
export default function OperatorReview({ initial, onChanged }) {
  const { toast } = useFeedback()
  const [v, setV] = useState(initial)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const update = next => { setV(next); onChanged?.() }

  async function viewAadhaar() {
    const tab = window.open('', '_blank')   // opened first, so pop-up blockers allow it
    try {
      const url = URL.createObjectURL(await apiBlob(`/admin/operators/${v.operator_id}/documents/aadhaar/file/`))
      if (tab) tab.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) { tab?.close(); toast(err.message, true) }
  }
  async function approve() {
    setBusy(true)
    try {
      await api(`/admin/operators/${v.operator_id}/verify/`, { method: 'POST', body: { verified: true } })
      update(await api(`/admin/operators/${v.operator_id}/verification/`)); toast(`${v.name} approved. Their packages can go live.`)
    } catch (err) { toast(err.message, true) } finally { setBusy(false) }
  }
  async function confirmPhone() {
    setBusy(true)
    try {
      update(await api(`/admin/operators/${v.operator_id}/phone/confirm/`, { method: 'POST' })); toast('Mobile number marked as verified')
    } catch (err) { toast(err.message, true) } finally { setBusy(false) }
  }
  async function reject() {
    setBusy(true)
    try {
      update(await api(`/admin/operators/${v.operator_id}/reject/`, { method: 'POST', body: { reason } }))
      toast(`${v.name}'s application sent back`); setRejecting(false)
    } catch (err) { toast(err.message, true) } finally { setBusy(false) }
  }

  return (
    <div className="text-[14px]">
      <div className="flex items-center gap-2 flex-wrap">
        <OpStatusBadge status={v.status} /><TierBadge tier={v.tier} />
        <span className="sub">{v.source === 'signup' ? 'Signed up themselves' : 'Added by admin'}{v.applied && ` · ${new Date(v.applied).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`}</span>
      </div>
      <div className="sub mt-1">{v.owner} · {v.city} · {v.email} · {v.phone.number}</div>
      {v.status === 'rejected' && <div className="note-box bg-danger-soft text-danger">Application sent back: {v.rejection_reason}</div>}

      <div className="mt-3">
        <div className="py-3 border-t border-line flex items-start gap-2 flex-wrap">
          <div className="flex-1 min-w-[180px]"><b>PAN + bank account</b>
            {v.bank && <div className="text-[13px]">{v.bank.bank_name} · {v.bank.account} · PAN {v.bank.pan}</div>}
            <Link className="link text-[13px]" to="/admin/payouts">Verify on the Payouts page →</Link></div>
          <Status status={v.bank?.status} />
        </div>
        <div className="py-3 border-t border-line flex items-start gap-2 flex-wrap">
          <div className="flex-1 min-w-[180px]"><b>Mobile number</b><div className="text-[13px]">{v.phone.number}</div>
            {!v.phone.verified && <button className="btn btn-sm btn-ghost-green mt-2" type="button" disabled={busy} onClick={confirmPhone}>
              <Icon name="check" size={13} /> Mark verified (I called {v.phone.number})</button>}</div>
          <Status status={v.phone.verified ? 'verified' : null} none="Not verified" />
        </div>
        <DocRow v={v} kind="aadhaar" title="Aadhaar (last 4 + masked copy)" onChange={update}>
          {v.documents.aadhaar?.has_file && <div><button className="link text-[13px]" type="button" onClick={viewAadhaar}><Icon name="eye" size={13} /> View masked copy</button></div>}
        </DocRow>
        <DocRow v={v} kind="gst" title="GST" onChange={update}>
          {v.documents.gst && <div className="text-[13px]">
            {v.gst_pan_match === true && <span style={{ color: 'var(--color-leaf)' }}>PAN in GSTIN matches the bank PAN. </span>}
            {v.gst_pan_match === false && <span style={{ color: 'var(--color-danger)' }}>PAN in GSTIN doesn't match the bank PAN. </span>}
            <a className="link" href="https://services.gst.gov.in/services/searchtp" target="_blank" rel="noreferrer">Check on the GST portal ↗</a></div>}
        </DocRow>
        <DocRow v={v} kind="udyam" title="Udyam (MSME)" onChange={update}>
          {v.documents.udyam && <div className="text-[13px]"><a className="link" href="https://udyamregistration.gov.in/Udyam_Verify.aspx" target="_blank" rel="noreferrer">Check on the Udyam portal ↗</a></div>}
        </DocRow>
      </div>

      {v.status === 'pending' && (
        <div className="pt-3 border-t border-line">
          {!v.tier && <div className="help mb-2">Approval needs at least Bronze: PAN + bank verified, plus a verified mobile number.</div>}
          {!rejecting ? (
            <div className="flex gap-2">
              <button className="btn btn-sm btn-ghost-green" type="button" disabled={busy || !v.tier} onClick={approve}>Approve operator</button>
              <button className="btn btn-sm btn-ghost-red" type="button" disabled={busy} onClick={() => setRejecting(true)}>Reject application</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input aria-label="Reason for rejecting the application" placeholder="Why? The operator sees this." maxLength={200} value={reason} onKeyDown={noEnter} onChange={e => setReason(e.target.value)} />
              <button className="btn btn-sm btn-danger flex-none" type="button" disabled={busy || reason.trim().length < 5} onClick={reject}>Reject</button>
              <button className="btn btn-sm flex-none" type="button" onClick={() => setRejecting(false)}>Cancel</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
