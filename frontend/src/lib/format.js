export const inr = n => '₹' + Math.round(Number(n) || 0).toLocaleString('en-IN')
export const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
export const fmtDate = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
export const fmtDay = d => new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
export const sum = (list, f) => list.reduce((s, x) => s + Number(f(x) || 0), 0)
export const durationLabel = n => `${n}N / ${Number(n) + 1}D`
export const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
export const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
