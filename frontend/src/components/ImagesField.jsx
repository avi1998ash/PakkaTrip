import { useEffect, useRef, useState } from 'react'
import { Icon } from './ui'

export const MIN_IMAGES = 4
export const MAX_IMAGES = 8
const MAX_BYTES = 5 * 1024 * 1024
const TYPES = ['image/jpeg', 'image/png', 'image/webp']
let seq = 0

/** Existing server images → editor items. */
export const toItems = images => images.map(img => ({ key: `e:${img.id}`, id: img.id, url: img.url }))

/**
 * Photo picker: 4–8 images, thumbnails, remove, choose cover, drag (or arrow buttons) to reorder.
 * items: [{ key, id? (existing), file? (new), url }]; cover: key of the cover item.
 */
export default function ImagesField({ items, onChange, cover, onCoverChange, onError }) {
  const inputRef = useRef(null)
  const [dragFrom, setDragFrom] = useState(null)
  const [dragOver, setDragOver] = useState(null)
  const created = useRef(new Set())

  // Free the in-memory previews of new files when the editor closes.
  useEffect(() => () => created.current.forEach(url => URL.revokeObjectURL(url)), [])

  function addFiles(fileList) {
    const room = MAX_IMAGES - items.length
    const files = [...fileList]
    const bad = files.find(f => !TYPES.includes(f.type)) || files.find(f => f.size > MAX_BYTES)
    if (bad) onError(TYPES.includes(bad.type) ? `“${bad.name}” is larger than 5 MB.` : `“${bad.name}” must be a JPG, PNG or WebP image.`)
    const ok = files.filter(f => TYPES.includes(f.type) && f.size <= MAX_BYTES)
    if (ok.length > room) onError(`You can add up to ${MAX_IMAGES} photos — ${ok.length - room} not added.`)
    const added = ok.slice(0, Math.max(0, room)).map(file => {
      const url = URL.createObjectURL(file)
      created.current.add(url)
      return { key: `n-${++seq}`, file, url }
    })
    if (!added.length) return
    const next = [...items, ...added]
    onChange(next)
    if (!cover || !next.some(i => i.key === cover)) onCoverChange(next[0].key)
  }

  function move(from, to) {
    if (to < 0 || to >= items.length || from === to) return
    const next = [...items]
    const [it] = next.splice(from, 1)
    next.splice(to, 0, it)
    onChange(next)
  }

  function remove(key) {
    const it = items.find(i => i.key === key)
    if (it?.file) { URL.revokeObjectURL(it.url); created.current.delete(it.url) }
    const next = items.filter(i => i.key !== key)
    onChange(next)
    if (cover === key) onCoverChange(next[0]?.key || '')
  }

  const count = items.length
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {items.map((it, i) => (
          <div key={it.key}
            draggable
            onDragStart={e => { setDragFrom(i); e.dataTransfer.effectAllowed = 'move' }}
            onDragOver={e => { e.preventDefault(); setDragOver(i) }}
            onDragLeave={() => setDragOver(o => (o === i ? null : o))}
            onDrop={e => { e.preventDefault(); move(dragFrom, i); setDragFrom(null); setDragOver(null) }}
            onDragEnd={() => { setDragFrom(null); setDragOver(null) }}
            className={`relative rounded-[10px] overflow-hidden border-2 bg-page cursor-grab active:cursor-grabbing transition
              ${cover === it.key ? 'border-saffron' : 'border-line'} ${dragOver === i && dragFrom !== i ? 'ring-4 ring-saffron/40' : ''} ${dragFrom === i ? 'opacity-40' : ''}`}>
            <img src={it.url} alt={`Photo ${i + 1}`} className="w-full aspect-[4/3] object-cover pointer-events-none select-none" />
            <span className="absolute top-1.5 left-1.5 bg-navy/85 text-white text-[11px] font-bold rounded-full px-2 py-0.5">{i + 1}</span>
            {cover === it.key
              ? <span className="absolute top-1.5 right-1.5 bg-saffron text-white text-[11px] font-bold rounded-full px-2 py-0.5">★ Cover</span>
              : <button type="button" onClick={() => onCoverChange(it.key)} className="absolute top-1.5 right-1.5 bg-white/90 text-navy text-[11px] font-bold rounded-full px-2 py-0.5 hover:bg-white">Set cover</button>}
            <div className="flex items-center justify-between bg-white px-1 py-1 border-t border-line">
              <div className="flex">
                <button type="button" className="icon-btn" onClick={() => move(i, i - 1)} disabled={i === 0} aria-label="Move left"><Icon name="left" size={16} /></button>
                <button type="button" className="icon-btn" onClick={() => move(i, i + 1)} disabled={i === count - 1} aria-label="Move right"><Icon name="right" size={16} /></button>
              </div>
              <button type="button" className="icon-btn text-danger" onClick={() => remove(it.key)} aria-label={`Remove photo ${i + 1}`}><Icon name="trash" size={16} /></button>
            </div>
          </div>
        ))}
        {count < MAX_IMAGES && (
          <button type="button" onClick={() => inputRef.current.click()}
            onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files) }}
            className="rounded-[10px] border-2 border-dashed border-line hover:border-saffron hover:bg-saffron-soft text-muted flex flex-col items-center justify-center gap-1 aspect-[4/3] cursor-pointer">
            <Icon name="upload" size={22} /><b className="text-ink text-[13px]">Add photos</b><span className="text-[11.5px]">JPG, PNG, WebP · max 5 MB</span>
          </button>
        )}
      </div>
      <input ref={inputRef} type="file" accept={TYPES.join(',')} multiple hidden onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
      <div className={`help mt-2 ${count < MIN_IMAGES ? '!text-danger' : ''}`}>
        {count} / {MAX_IMAGES} photos · at least {MIN_IMAGES} needed. Drag to reorder (or use the arrows); the cover photo is shown first to travellers.
      </div>
    </div>
  )
}
