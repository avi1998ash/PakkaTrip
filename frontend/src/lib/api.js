// Small fetch wrapper: adds the JWT, refreshes it once on 401, and turns API errors into readable messages.
const KEY = 'pakkatrip_tokens'

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') } catch { return null }
}
let tokens = load()
let refreshing = null
let onAuthLost = () => {}

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

export function setTokens(t) {
  tokens = t
  try { t ? localStorage.setItem(KEY, JSON.stringify(t)) : localStorage.removeItem(KEY) } catch { /* storage blocked */ }
}
export const hasTokens = () => !!tokens
export const setAuthLostHandler = fn => { onAuthLost = fn }

function messageFrom(data) {
  if (!data) return null
  if (typeof data.detail === 'string') return data.detail
  const first = Object.values(data)[0]       // DRF field errors: { field: ["msg"] }
  if (Array.isArray(first)) return String(first[0])
  if (first && typeof first === 'object') return messageFrom(first)
  return typeof first === 'string' ? first : null
}

async function refreshTokens() {
  refreshing ??= fetch('/api/auth/refresh/', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: tokens?.refresh }),
  }).then(async r => {
    if (!r.ok) { setTokens(null); return false }
    const d = await r.json()
    setTokens({ access: d.access, refresh: d.refresh || tokens.refresh })
    return true
  }).finally(() => { refreshing = null })
  return refreshing
}

export async function api(path, { method = 'GET', body } = {}) {
  const isForm = body instanceof FormData   // file uploads: let the browser set the multipart boundary
  const send = () => fetch('/api' + path, {
    method,
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...(tokens ? { Authorization: 'Bearer ' + tokens.access } : {}) },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  let r = await send()
  if (r.status === 401 && tokens?.refresh && !path.startsWith('/auth/login')) {
    if (await refreshTokens()) r = await send()
    else {
      onAuthLost()
      // Public pages work without an account: retry anonymously instead of failing.
      if (path.startsWith('/public/')) r = await send()
      else throw new ApiError('Your session has expired. Please sign in again.', 401)
    }
  }
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new ApiError(messageFrom(data) || `Request failed (${r.status})`, r.status)
  return data
}
