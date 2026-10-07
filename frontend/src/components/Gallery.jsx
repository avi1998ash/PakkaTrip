import { useEffect, useState } from 'react'
import { Icon } from './ui'

/** Cover first; click any photo for a full-screen viewer (arrow keys / Esc). */
export function orderedImages(images = []) {
  const cover = images.find(i => i.is_cover)
  return cover ? [cover, ...images.filter(i => i !== cover)] : images
}

export function Lightbox({ images, index, onClose, onIndex }) {
  useEffect(() => {
    const onKey = e => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') onIndex((index + 1) % images.length)
      if (e.key === 'ArrowLeft') onIndex((index - 1 + images.length) % images.length)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [index, images.length, onClose, onIndex])

  return (
    <div className="fixed inset-0 z-[70] bg-black/90 flex flex-col" role="dialog" aria-modal="true" aria-label="Photo viewer" onClick={onClose}>
      <div className="flex justify-between items-center text-white px-4 py-3">
        <span className="text-sm">{index + 1} / {images.length}</span>
        <button className="icon-btn !text-white hover:!bg-white/10" onClick={onClose} aria-label="Close"><Icon name="x" size={22} /></button>
      </div>
      <div className="flex-1 flex items-center justify-center gap-2 px-2 min-h-0" onClick={e => e.stopPropagation()}>
        <button className="icon-btn !text-white hover:!bg-white/10" onClick={() => onIndex((index - 1 + images.length) % images.length)} aria-label="Previous photo"><Icon name="left" size={30} /></button>
        <img src={images[index].url} alt={`Photo ${index + 1}`} className="max-h-full max-w-[calc(100%-100px)] object-contain rounded-lg" />
        <button className="icon-btn !text-white hover:!bg-white/10" onClick={() => onIndex((index + 1) % images.length)} aria-label="Next photo"><Icon name="right" size={30} /></button>
      </div>
      <div className="flex gap-2 justify-center p-3 overflow-x-auto" onClick={e => e.stopPropagation()}>
        {images.map((img, i) => (
          <button key={img.id ?? i} onClick={() => onIndex(i)} className={`flex-none rounded-md overflow-hidden border-2 ${i === index ? 'border-saffron' : 'border-transparent opacity-60'}`}>
            <img src={img.url} alt="" className="w-16 h-12 object-cover" />
          </button>
        ))}
      </div>
    </div>
  )
}

// Fill the 2×2 area beside the cover with however many photos there are (no empty tiles).
function spanFor(count, i) {
  if (count === 1) return 'sm:col-span-2 sm:row-span-2'
  if (count === 2) return 'sm:col-span-2'
  if (count === 3 && i === 2) return 'sm:col-span-2'
  return ''
}

export default function Gallery({ images, small }) {
  const list = orderedImages(images)
  const [open, setOpen] = useState(null)
  if (!list.length) return <div className="sub">No photos uploaded.</div>
  const [main, ...rest] = list
  return (
    <>
      {small ? (
        <div className="grid grid-cols-4 gap-1.5">
          {list.map((img, i) => (
            <button key={img.id} type="button" onClick={() => setOpen(i)} className="relative rounded-md overflow-hidden">
              <img src={img.url} alt={`Photo ${i + 1}`} className="w-full aspect-[4/3] object-cover" />
              {i === 0 && <span className="absolute top-1 left-1 bg-saffron text-white text-[10px] font-bold rounded-full px-1.5">Cover</span>}
            </button>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-4 grid-rows-2 gap-2 h-[260px] sm:h-[380px] rounded-[14px] overflow-hidden">
          <button type="button" onClick={() => setOpen(0)} className={`col-span-4 row-span-2 relative ${rest.length ? 'sm:col-span-2' : ''}`}>
            <img src={main.url} alt="Cover photo" className="w-full h-full object-cover" />
          </button>
          {rest.slice(0, 4).map((img, i, shown) => (
            <button key={img.id} type="button" onClick={() => setOpen(i + 1)}
              className={`hidden sm:block relative ${spanFor(shown.length, i)}`}>
              <img src={img.url} alt={`Photo ${i + 2}`} className="w-full h-full object-cover" />
              {i === 3 && list.length > 5 && <span className="absolute inset-0 bg-black/50 text-white grid place-items-center font-semibold">+{list.length - 5} more</span>}
            </button>
          ))}
        </div>
      )}
      {!small && <button type="button" className="btn btn-sm mt-2" onClick={() => setOpen(0)}><Icon name="image" size={15} /> {list.length === 1 ? 'View photo' : `View all ${list.length} photos`}</button>}
      {open !== null && <Lightbox images={list} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />}
    </>
  )
}
