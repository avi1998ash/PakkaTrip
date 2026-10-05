import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useFeedback } from '../components/feedback'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import '../public.css'
import { firstName, initials, PIcon } from './shared'

const Mark = () => (
  <span className="brand-mark"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
)

export function PolicyTable({ policy }) {
  return (
    <>
      <table className="policy-table"><tbody>
        {policy.map(r => <tr key={r.min_days}><td>{r.label}</td><td>{r.pct}% refund</td></tr>)}
        <tr><td>Operator cancels the trip</td><td style={{ color: 'var(--green)' }}>100% + fee refunded</td></tr>
      </tbody></table>
      <p className="help">Refunds are on the package amount. The convenience fee is non-refundable when you cancel. Refunds reach your original payment method in 5–7 working days.</p>
    </>
  )
}

export default function PublicLayout() {
  const { user, logout } = useAuth()
  const { toast } = useFeedback()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)
  const traveller = user?.role === 'traveller' ? user : null

  useEffect(() => { setMenu(false); if (!window.location.hash) window.scrollTo(0, 0) }, [pathname])
  const [cfg, setCfg] = useState(null)
  useEffect(() => { api('/public/config/').then(setCfg, () => {}) }, [])
  const site = cfg?.site

  return (
    <div className="pub min-h-screen">
      <header className="site-header">
        <div className="container">
          <Link className="brand" to="/" aria-label="PakkaTrip home"><Mark /><span>Pakka<b>Trip</b></span></Link>
          <nav className="main-nav">
            <NavLink to="/" end>Home</NavLink>
            <NavLink to="/search">Explore trips</NavLink>
            <NavLink to="/my-bookings">My Bookings</NavLink>
          </nav>
          <div className="header-right">
            <a className="hdr-link wide" href="/partner/login">For operators</a>
            <Link className="hdr-icon" to="/my-bookings" aria-label="My bookings"><PIcon name="ticket" size={20} /></Link>
            {traveller ? (
              <button className="user-btn" onClick={() => setMenu(m => !m)} aria-haspopup="true" aria-expanded={menu}>
                <span className="avatar">{initials(traveller.name)}</span><span className="nm">{firstName(traveller.name)}</span>
              </button>
            ) : <Link className="btn btn-primary btn-sm" to={`/account?next=${encodeURIComponent(pathname)}`}>Login</Link>}
          </div>
        </div>
        {menu && traveller && (
          <div className="menu" onMouseLeave={() => setMenu(false)}>
            <div className="who"><b>{traveller.name}</b>{traveller.email}</div>
            <Link to="/my-bookings">My Bookings</Link>
            <Link to="/search">Explore trips</Link>
            <button onClick={() => { logout(); toast('Logged out'); navigate('/') }}>Log out</button>
          </div>
        )}
      </header>

      <main><Outlet /></main>

      <footer>
        <div className="container">
          <div className="foot-grid">
            <div className="foot-about">
              <Link className="brand" to="/"><Mark /><span>Pakka<b>Trip</b></span></Link>
              <p>Compare trip packages from verified local operators and book your seat in minutes — no WhatsApp back-and-forth, no hidden charges.</p>
            </div>
            <div><h4>Explore</h4>
              <Link to="/search?from=Delhi&to=Manali">Delhi → Manali</Link>
              <Link to="/search?from=Delhi&to=Rishikesh">Delhi → Rishikesh</Link>
              <Link to="/search?from=Mumbai&to=Goa">Mumbai → Goa</Link>
              <Link to="/search">All trips</Link></div>
            <div><h4>Help</h4>
              <Link to="/my-bookings">My Bookings</Link>
              <Link to="/refund-policy">Cancellation & refunds</Link>
              <Link to="/contact">Contact us</Link>
              {site?.support_phone && <a href={`tel:${site.support_phone.replace(/\s/g, '')}`}>{site.support_phone}</a>}
              {site?.support_email && <a href={`mailto:${site.support_email}`}>{site.support_email}</a>}</div>
            <div><h4>Company</h4>
              <a href="/partner/signup">List your trips (operators)</a>
              <Link to="/terms">Terms of use</Link>
              <Link to="/privacy">Privacy policy</Link>
              <Link to="/terms#delivery">Booking delivery</Link></div>
          </div>
          <div className="foot-bottom">
            <span>© {new Date().getFullYear()} {site?.legal_name || 'PakkaTrip'} · Made in India for Indian travellers</span>
            {cfg?.payments_test_mode && <span className="demo-flag">Razorpay test mode — no real money moves</span>}
          </div>
        </div>
      </footer>
    </div>
  )
}
