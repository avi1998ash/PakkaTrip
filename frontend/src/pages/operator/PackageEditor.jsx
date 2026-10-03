import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FacilitiesField } from '../../components/Facilities'
import { useFeedback } from '../../components/feedback'
import ImagesField, { MAX_IMAGES, MIN_IMAGES, toItems } from '../../components/ImagesField'
import { Badge, Icon, LoadError, Loading } from '../../components/ui'
import { api } from '../../lib/api'

const EMPTY = { title: '', from_city: '', to_city: '', nights: 1, price: '', default_seats: 20 }

/** Full-page add / edit form for an operator's package: basics, 4–8 photos, facilities. */
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
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const load = [api('/operator/facility-options/'), editing ? api(`/operator/packages/${id}/`) : Promise.resolve(null)]
    Promise.all(load).then(([opts, p]) => {
      setOptions(opts)
      if (p) {
        setPkg(p)
        setBasics({ title: p.title, from_city: p.from_city, to_city: p.to_city, nights: p.nights, price: p.price, default_seats: p.default_seats })
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

      {!editing && <div className="note-box !mt-0 bg-amber-soft text-amber">New packages start as <b>Pending review</b> and go live once PakkaTrip approves them.</div>}

      <div className="fixed bottom-0 left-0 right-0 lg:left-[244px] bg-white border-t border-line px-4 lg:px-6 py-3 flex justify-end gap-2.5 z-10">
        <Link to="/operator/packages" className="btn">Cancel</Link>
        <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Submit for review'}</button>
      </div>
    </form>
  )
}
