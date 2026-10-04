import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui'
import { useAuth } from '../../lib/auth'

export function UnverifiedBanner() {
  const { user } = useAuth()
  const op = user.operator
  if (!op || op.verified) return null
  if (op.status === 'rejected') return (
    <div className="banner" style={{ background: 'var(--color-danger-soft)', color: 'var(--color-danger)' }}><Icon name="alert" size={20} />
      <div className="flex-1">Your application was sent back: <b>{op.rejection_reason}</b></div>
      <Link className="btn btn-sm" to="/operator/verification">Fix and resubmit</Link>
    </div>
  )
  return (
    <div className="banner"><Icon name="alert" size={20} />
      <div className="flex-1">Your account is <b>awaiting approval</b>. You can set up packages now; travellers see them once PakkaTrip approves you
        (needs at least Bronze: PAN + bank + mobile).</div>
      <Link className="btn btn-sm" to="/operator/verification">Verification</Link>
    </div>
  )
}
