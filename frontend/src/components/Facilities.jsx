import { useState } from 'react'
import { Icon } from './ui'

export const FACILITY_SECTIONS = [
  ['meals', 'Meals', 'meal'],
  ['accommodation', 'Accommodation', 'bed'],
  ['transport', 'Transport', 'bus'],
  ['activities', 'Activities', 'bolt'],
  ['places', 'Visiting places', 'pin'],
  ['other', 'Other', 'check'],
]
const CUSTOM = { places: 'e.g. Solang Valley', other: 'e.g. Free photo session' }

function AddItem({ placeholder, onAdd }) {
  const [text, setText] = useState('')
  const add = () => { const t = text.trim().replace(/\s+/g, ' '); if (t) { onAdd(t); setText('') } }
  return (
    <div className="flex gap-2 mt-2">
      <input type="text" value={text} maxLength={80} placeholder={placeholder} onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
      <button type="button" className="btn" onClick={add} disabled={!text.trim()}><Icon name="plus" size={15} /> Add</button>
    </div>
  )
}

/** Checkbox chips for standard items + free-text "Add" for visiting places and other extras. */
export function FacilitiesField({ options, value, onChange }) {
  const set = (cat, labels) => onChange({ ...value, [cat]: labels })
  const toggle = (cat, label) => {
    const cur = value[cat] || []
    set(cat, cur.includes(label) ? cur.filter(l => l !== label) : [...cur, label])
  }
  const addCustom = (cat, label) => {
    const cur = value[cat] || []
    if (!cur.some(l => l.toLowerCase() === label.toLowerCase())) set(cat, [...cur, label])
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {FACILITY_SECTIONS.map(([cat, title, icon]) => {
        const chosen = value[cat] || []
        const standard = options[cat] || []
        const custom = chosen.filter(l => !standard.includes(l))
        return (
          <fieldset key={cat} className={cat === 'places' ? 'sm:col-span-2' : ''}>
            <legend className="flex items-center gap-2 font-semibold text-[14px] mb-2"><span className="text-navy-2"><Icon name={icon} size={17} /></span>{title}
              {chosen.length > 0 && <span className="badge b-navy !text-[11px]">{chosen.length}</span>}</legend>
            {standard.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {standard.map(label => {
                  const on = chosen.includes(label)
                  return (
                    <button key={label} type="button" onClick={() => toggle(cat, label)} aria-pressed={on}
                      className={`chip inline-flex items-center gap-1 ${on ? '!bg-leaf-soft !border-leaf !text-leaf' : ''}`}>
                      {on && <Icon name="check" size={13} />}{label}</button>
                  )
                })}
              </div>
            )}
            {CUSTOM[cat] && (
              <>
                {custom.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {custom.map((label, i) => (
                      <span key={label} className="chip !cursor-default inline-flex items-center gap-1.5 !bg-saffron-soft !border-saffron/40">
                        {cat === 'places' && <b className="text-saffron-dark">{i + 1}</b>}{label}
                        <button type="button" className="text-muted hover:text-danger leading-none" onClick={() => set(cat, chosen.filter(l => l !== label))} aria-label={`Remove ${label}`}>×</button>
                      </span>
                    ))}
                  </div>
                )}
                <AddItem placeholder={CUSTOM[cat]} onAdd={label => addCustom(cat, label)} />
              </>
            )}
          </fieldset>
        )
      })}
    </div>
  )
}

/** Read-only list (admin review, traveller page). */
export function FacilitiesView({ facilities, compact }) {
  const sections = FACILITY_SECTIONS.filter(([cat]) => facilities?.[cat]?.length)
  if (!sections.length) return <p className="sub m-0">No facilities listed yet.</p>
  return (
    <div className={`grid gap-4 ${compact ? '' : 'sm:grid-cols-2'}`}>
      {sections.map(([cat, title, icon]) => (
        <div key={cat} className={cat === 'places' && !compact ? 'sm:col-span-2' : ''}>
          <div className="flex items-center gap-2 font-semibold text-[13.5px] mb-1.5">
            <span className="w-7 h-7 rounded-lg bg-navy-soft text-navy-2 grid place-items-center"><Icon name={icon} size={15} /></span>{title}</div>
          {cat === 'places' ? (
            <ol className="flex flex-wrap gap-1.5 m-0 p-0 list-none">
              {facilities.places.map((p, i) => <li key={p} className="chip !cursor-default !bg-saffron-soft !border-saffron/30 text-[#8A4B0F]"><b>{i + 1}.</b> {p}</li>)}
            </ol>
          ) : (
            <ul className="flex flex-wrap gap-x-4 gap-y-1 m-0 p-0 list-none text-[14px]">
              {facilities[cat].map(l => <li key={l} className="flex items-center gap-1.5"><span className="text-leaf"><Icon name="check" size={15} /></span>{l}</li>)}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}
