import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FacilitiesField } from '../../components/Facilities'
import { useFeedback } from '../../components/feedback'
import ImagesField, { MAX_IMAGES, MIN_IMAGES, toItems } from '../../components/ImagesField'
import { Badge, Icon, LoadError, Loading } from '../../components/ui'
import { api } from '../../lib/api'

const EMPTY = { title: '', from_city: '', to_city: '', nights: 1, price: '', default_seats: 20, pickup_point: '' }
const BLANK_DAY = { title: '', text: '' }
const dayCount = nights => Math.min(16, Math.max(1, (parseInt(nights, 10) || 0) + 1))   // 0 nights = a day trip

/** Full-page add / edit form for an operator's package: basics + pickup, 4–8 photos, facilities, day-wise itinerary. */
export default function PackageEditor() {
  const { id } = useParams()
  const editing = !!id
  const navigate = useNavigate()
  const { toast } = useFeedback()
  const [options, setOptions] = useState(null)
  const [pkg, setPkg] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [basics, setBasics] = useState(EMPTY)
  const [images, setImages] = useState([])
  const [cover, setCover] = useState('')
  const [facilities, setFacilities] = useState({})
  const [days, setDays] = useState([])   // may hold more days than the trip has; trimmed on save
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const load = [api('/operator/facility-options/'), editing ? api(`/operator/packages/${id}/`) : Promise.resolve(null)]
    Promise.all(load).then(([opts, p]) => {
      setOptions(opts)
      if (p) {
        setPkg(p)
        setBasics({ title: p.title, from_city: p.from_city, to_city: p.to_city, nights: p.nights, price: p.price, default_seats: p.default_seats,
          pickup_point: p.pickup_point || '' })
        setDays((p.itinerary || []).map(d => ({ title: d.title, text: d.text || '' })))
        setImages(toItems(p.images))
        setCover(p.images.find(i => i.is_cover) ? `e:${p.images.find(i => i.is_cover).id}` : p.images[0] ? `e:${p.images[0].id}` : '')
        setFacilities(p.facilities)
      }
    }, setLoadError)
  }, [id, editing])

  if (loadError) return <LoadError error={loadError} retry={() => window.location.reload()} />
  if (!options) return <Loading />

  const field = (key, props) => <input {...props} value={basics[key]} onChange={e => setBasics(b => ({ ...b, [key]: e.target.value }))} />
  const showError = msg => { setError(msg); toast(msg, true) }
  const nDays = dayCount(basics.nights)
  const tripDays = Array.from({ length: nDays }, (_, i) => days[i] || BLANK_DAY)
  const itineraryStarted = tripDays.some(d => d.title.trim() || d.text.trim())
  const setDay = (i, key, value) => setDays(ds => {
    const next = Array.from({ length: Math.max(ds.length, i + 1) }, (_, j) => ds[j] || BLANK_DAY)
    next[i] = { ...next[i], [key]: value }
    return next
  })

  async function submit(e) {
    e.preventDefault()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    if (images.length < MIN_IMAGES || images.length > MAX_IMAGES) {
      showError(`Add between ${MIN_IMAGES} and ${MAX_IMAGES} photos (you have ${images.length}).`)
      document.getElementById('photos')?.scrollIntoView({ behavior: 'smooth' })
      return
    }
    // Existing photos are referenced by id ("e:12"); new files by their position in new_images ("n:0").
    const fd = new FormData()
    Object.entries(basics).forEach(([k, v]) => fd.append(k, String(v).trim()))
    const tokens = []
    let coverToken = ''
    let n = 0
    for (const it of images) {
      const token = it.file ? `n:${n++}` : it.key
      if (it.file) fd.append('new_images', it.file)
      if (it.key === cover) coverToken = token
      tokens.push(token)
    }
    fd.append('images', JSON.stringify(tokens))
    fd.append('cover', coverToken || tokens[0])
    fd.append('facilities', JSON.stringify(facilities))
    // Always sent: the server replaces the itinerary on every save (an empty list = use the generic day plan).
    fd.append('itinerary', JSON.stringify(itineraryStarted ? tripDays.map(d => ({ title: d.title.trim(), text: d.text.trim() })) : []))

    setSaving(true); setError('')
    try {
      await api(editing ? `/operator/packages/${id}/` : '/operator/packages/', { method: editing ? 'PATCH' : 'POST', body: fd })
      toast(editing ? 'Package updated' : 'Package submitted — PakkaTrip will review it')
      navigate('/operator/packages')
    } catch (err) { showError(err.message) } finally { setSaving(false) }
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5 max-w-[920px] pb-20">
      <div className="flex items-center gap-3 flex-wrap">
        <Link to="/operator/packages" className="link inline-flex items-center gap-1"><Icon name="left" size={16} /> My Packages</Link>
        <h3 className="text-[19px] font-semibold flex-1">{editing ? `Edit “${pkg.title}”` : 'Add a new package'}</h3>
        {pkg && <Badge status={pkg.status} pkg />}
      </div>
      {pkg?.status === 'rejected' && pkg.rejection_reason && <div className="banner !bg-danger-soft !text-danger"><Icon name="alert" size={20} />Rejected: {pkg.rejection_reason}</div>}
      {error && <div className="form-error !mb-0" role="alert">{error}</div>}

      <section className="card p-[18px]">
        <h4 className="font-semibold text-[15.5px] mb-3.5">Trip details</h4>
        <div className="form-grid">
          <div className="full"><label htmlFor="title">Package title</label>{field('title', { id: 'title', type: 'text', required: true, maxLength: 70, placeholder: 'e.g. Manali Weekend Escape' })}</div>
          <div><label htmlFor="from">From</label>{field('from_city', { id: 'from', type: 'text', required: true, maxLength: 40, placeholder: 'Delhi' })}</div>
          <div><label htmlFor="to">To</label>{field('to_city', { id: 'to', type: 'text', required: true, maxLength: 40, placeholder: 'Manali' })}</div>
          <div><label htmlFor="nights">Nights</label>{field('nights', { id: 'nights', type: 'number', required: true, min: 0, max: 15 })}</div>
          <div><label htmlFor="price">Price per person (₹)</label>{field('price', { id: 'price', type: 'number', required: true, min: 1, step: 1 })}</div>
          <div><label htmlFor="seats">Default seats per departure</label>{field('default_seats', { id: 'seats', type: 'number', required: true, min: 1, max: 80 })}</div>
          <div className="full"><label htmlFor="pickup">Pickup point & time</label>{field('pickup_point', { id: 'pickup', type: 'text', maxLength: 160, placeholder: 'e.g. Majnu ka Tilla, Delhi · 7:30 PM' })}
            <p className="help">Shown on the trip page, the ticket and the confirmation email. Leave blank if you'll share it after booking.</p></div>
        </div>
      </section>

      <section className="card p-[18px]" id="photos">
        <h4 className="font-semibold text-[15.5px]">Photos</h4>
        <p className="help !mt-0.5 mb-3.5">Real photos of the bus, stay and places build trust. Add {MIN_IMAGES}–{MAX_IMAGES}.</p>
        <ImagesField items={images} onChange={setImages} cover={cover} onCoverChange={setCover} onError={showError} />
      </section>

      <section className="card p-[18px]">
        <h4 className="font-semibold text-[15.5px]">Facilities & inclusions</h4>
        <p className="help !mt-0.5 mb-4">Tick what's included in the price. Travellers compare packages on these.</p>
        <FacilitiesField options={options} value={facilities} onChange={setFacilities} />
      </section>

      <section className="card p-[18px]" id="itinerary">
        <h4 className="font-semibold text-[15.5px]">Day-wise itinerary</h4>
        <p className="help !mt-0.5 mb-4">
          {nDays} day{nDays === 1 ? '' : 's'} for {Number(basics.nights) || 0} night{Number(basics.nights) === 1 ? '' : 's'}. Optional, but travellers book more when they can see the plan.
          {itineraryStarted && ' Give every day a title.'}
        </p>
        <div className="flex flex-col gap-3.5">
          {tripDays.map((d, i) => (
            <div key={i} className="grid grid-cols-[52px_1fr] gap-3 items-start">
              <div className="rounded-lg bg-saffron-soft text-[#7A4510] font-bold text-center py-2 text-[13px] leading-tight">Day<br />{i + 1}</div>
              <div className="flex flex-col gap-2">
                <input type="text" aria-label={`Day ${i + 1} title`} required={itineraryStarted} maxLength={140} value={d.title}
                  placeholder={i === 0 ? `e.g. ${basics.from_city || 'Delhi'} → ${basics.to_city || 'Manali'} overnight` : i === nDays - 1 ? 'e.g. Return journey' : 'e.g. Solang Valley & Hadimba Temple'}
                  onChange={e => setDay(i, 'title', e.target.value)} />
                <textarea rows={2} aria-label={`Day ${i + 1} details`} maxLength={1500} value={d.text} placeholder="Timings, places, meals, stay…"
                  onChange={e => setDay(i, 'text', e.target.value)} />
              </div>
            </div>
          ))}
        </div>
      </section>

      {!editing && <div className="note-box !mt-0 bg-amber-soft text-amber">New packages start as <b>Pending review</b> and go live once PakkaTrip approves them.</div>}

      <div className="fixed bottom-0 left-0 right-0 lg:left-[244px] bg-white border-t border-line px-4 lg:px-6 py-3 flex justify-end gap-2.5 z-10">
        <Link to="/operator/packages" className="btn">Cancel</Link>
        <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Submit for review'}</button>
      </div>
    </form>
  )
}
