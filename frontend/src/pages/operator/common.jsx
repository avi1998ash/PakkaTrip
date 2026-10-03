import { Icon } from '../../components/ui'
import { useAuth } from '../../lib/auth'

export function UnverifiedBanner() {
  const { user } = useAuth()
  if (user.operator?.verified) return null
  return (
    <div className="banner"><Icon name="alert" size={20} />
      <div>Your account is <b>awaiting verification</b>. Packages go live once PakkaTrip verifies your documents.</div>
    </div>
  )
}
