import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, hasTokens, setAuthLostHandler, setTokens } from './api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(!hasTokens())

  useEffect(() => {
    setAuthLostHandler(() => setUser(null))
    if (!hasTokens()) return
    api('/auth/me/').then(setUser).catch(() => setTokens(null)).finally(() => setReady(true))
  }, [])

  const login = useCallback(async (email, password) => {
    const d = await api('/auth/login/', { method: 'POST', body: { email, password } })
    setTokens({ access: d.access, refresh: d.refresh })
    setUser(d.user)
    return d.user
  }, [])

  /** Use tokens from another login endpoint (traveller login / signup). */
  const adopt = useCallback(d => { setTokens({ access: d.access, refresh: d.refresh }); setUser(d.user); return d.user }, [])
  const logout = useCallback(() => { setTokens(null); setUser(null) }, [])
  const refreshMe = useCallback(() => api('/auth/me/').then(setUser), [])

  return <AuthCtx.Provider value={{ user, ready, login, adopt, logout, refreshMe }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
export const homeFor = user => ({ admin: '/admin/dashboard', operator: '/operator/dashboard' }[user?.role] || '/my-bookings')
export const isPortalUser = user => user?.role === 'admin' || user?.role === 'operator'
