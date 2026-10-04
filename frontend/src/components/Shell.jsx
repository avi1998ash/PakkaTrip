import { useCallback, useEffect, useState } from 'react'
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { homeFor, useAuth } from '../lib/auth'
import { useFeedback } from './feedback'
import { Brand, Icon } from './ui'

export const NAV = {
  admin: [['dashboard', 'Dashboard', 'grid'], ['operators', 'Operators', 'users'], ['packages', 'Packages', 'box'], ['bookings', 'Bookings', 'ticket'], ['payouts', 'Payouts', 'bank'], ['settings', 'Settings', 'cog']],
  operator: [['dashboard', 'My Dashboard', 'grid'], ['packages', 'My Packages', 'box'], ['inventory', 'Seat Inventory', 'seat'], ['bookings', 'My Bookings', 'ticket'], ['earnings', 'My Earnings', 'wallet'], ['bank', 'Bank & Payouts', 'bank'], ['reviews', 'Reviews', 'star']],
}
const COUNT_KEY = { operator: { bookings: 'op-bookings', reviews: 'reviews' }, admin: { operators: 'operators', packages: 'packages', bookings: 'bookings', payouts: 'payouts' } }

/** Route guard: no session → login; wrong role → back to the user's own pages. */
export function RequireRole({ role, children }) {
  const { user, ready } = useAuth()
  if (!ready) return <div className="empty">Loading…</div>
  if (!user) return <Navigate to="/partner/login" replace />
  if (user.role !== role) return <Navigate to={homeFor(user)} replace />
  return children
}

export default function Shell() {
  const { user, logout, refreshMe } = useAuth()
  const { toast } = useFeedback()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [counts, setCounts] = useState({})
  const role = user.role
  const base = `/${role}`
  const op = user.operator

  const refreshCounts = useCallback(() => api(`${base}/nav-counts/`).then(setCounts).catch(() => {}), [base])
  useEffect(() => { refreshCounts(); setOpen(false) }, [pathname, refreshCounts])
  // An operator's verified badge can change while they're signed in (admin verifies them).
  useEffect(() => { if (role === 'operator') refreshMe().catch(() => {}) }, [pathname, role, refreshMe])

  const current = NAV[role].find(([id]) => pathname.startsWith(`${base}/${id}`))
  const signOut = () => { logout(); navigate('/partner/login', { replace: true }); toast('Signed out') }

  return (
    <div className="lg:grid lg:grid-cols-[244px_1fr] min-h-screen">
      <aside className={`bg-navy text-[#DCE6F4] p-[20px_14px] flex flex-col gap-[18px] fixed inset-y-0 left-0 w-64 z-40 transition-transform
        lg:sticky lg:top-0 lg:h-screen lg:w-auto lg:translate-x-0 overflow-y-auto ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <Brand className="text-white px-1.5" />
        <div className="mx-1.5 px-2.5 py-2 rounded-[10px] bg-white/[.07] text-[12.5px]">
          {op ? 'Operator' : 'Signed in as'}
          <b className="block text-white text-[13.5px] truncate">{op ? op.name : 'Administrator'}</b>
        </div>
        <nav className="nav flex flex-col gap-1">
          {NAV[role].map(([id, label, icon]) => {
            const n = counts[COUNT_KEY[role][id]]
            return (
              <NavLink key={id} to={`${base}/${id}`} className={({ isActive }) => (isActive ? 'active' : '')}>
                <Icon name={icon} />{label}{n > 0 && <span className="count">{n}</span>}
              </NavLink>
            )
          })}
        </nav>
        <div className="mt-auto text-xs text-[#8FA4C2] px-1.5">PakkaTrip Partner Portal</div>
      </aside>
      {open && <div className="fixed inset-0 bg-[rgb(11_24_45/.45)] z-30 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="min-w-0 flex flex-col">
        <header className="flex items-center gap-3 px-4 lg:px-6 py-3 lg:py-3.5 bg-white border-b border-line sticky top-0 z-[5]">
          <button className="icon-btn lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
          <h2 className="text-lg font-semibold">{current?.[1]}</h2>
          <div className="flex-1" />
          <div className="flex items-center gap-2.5">
            <div className="text-right leading-tight hidden sm:block">
              {op ? op.owner : 'Admin'}<small className="text-muted block text-[11.5px]">{user.email}</small>
            </div>
            <div className={`w-[34px] h-[34px] rounded-full grid place-items-center text-white font-bold text-[13px] ${op ? 'bg-saffron' : 'bg-navy'}`}>
              {(op ? op.name : 'A').charAt(0).toUpperCase()}
            </div>
          </div>
          <button className="icon-btn" onClick={signOut} title="Sign out" aria-label="Sign out"><Icon name="logout" /></button>
        </header>
        <main className="p-4 lg:p-6 flex flex-col gap-5">
          <Outlet context={{ refreshCounts }} />
        </main>
      </div>
    </div>
  )
}
