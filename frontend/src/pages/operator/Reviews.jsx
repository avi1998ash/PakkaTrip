import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useFeedback } from '../../components/feedback'
import { Chips, LoadError, Loading, Stars } from '../../components/ui'
import { api } from '../../lib/api'
import { fmtDate, plural } from '../../lib/format'
import { useApi } from '../../lib/useApi'

export default function OpReviews() {
  const [f, setF] = useState('all')
  const { data: d, error, reload } = useApi(`/operator/reviews/?filter=${f}`)
  const { open, toast } = useFeedback()
  const { refreshCounts } = useOutletContext()
  if (error) return <LoadError error={error} retry={reload} />
  if (!d) return <Loading />

  const reply = r => open({ title: `Reply to ${r.customer}`, submitLabel: 'Post reply', body: (
    <>
      <p className="mt-0 mb-3"><Stars rating={r.rating} /><br />{r.text}</p>
      <label>Your public reply</label>
      <textarea name="reply" maxLength={400} defaultValue={r.reply} placeholder="Thank the customer or explain what you've fixed" />
    </>
  ), onSubmit: async x => {
    const saved = await api(`/operator/reviews/${r.id}/reply/`, { method: 'POST', body: { reply: x.reply } })
    toast(saved.reply ? 'Reply posted' : 'Reply removed'); reload(); refreshCounts()
  } })

  const avg = d.avg ?? 0
  return (
    <>
      <div className="card p-[18px]">
        <div className="grid sm:grid-cols-[auto_1fr] gap-6 items-center">
          <div className="text-center">
            <b className="font-display text-[40px] block leading-[1.1]">{d.count ? avg.toFixed(1) : '—'}</b>
            <Stars rating={Math.round(avg)} /><div className="sub">{plural(d.count, 'review')}</div>
          </div>
          <div>
            {[5, 4, 3, 2, 1].map(n => (
              <div key={n} className="dist-row"><span>{n} ★</span>
                <div className="bar"><span style={{ width: `${d.count ? d.distribution[n] / d.count * 100 : 0}%` }} /></div>
                <span>{d.distribution[n]}</span></div>
            ))}
          </div>
        </div>
      </div>
      <div className="toolbar"><Chips value={f} onChange={setF} options={[['all', 'All'], ['unreplied', 'Needs reply'], ['low', '3 ★ and below']]} /></div>
      <div className="card">
        {d.items.length ? d.items.map(r => (
          <div key={r.id} className="review">
            <div className="flex justify-between gap-2.5 flex-wrap">
              <div><b>{r.customer}</b> · <Stars rating={r.rating} />
                <div className="sub">{r.package_title} · {fmtDate(r.date)} · booking {r.booking_id}</div></div>
              <button className="btn btn-sm" onClick={() => reply(r)}>{r.reply ? 'Edit reply' : 'Reply'}</button>
            </div>
            <p className="mt-1.5 mb-0">{r.text}</p>
            {r.reply && <div className="reply"><b>Your reply:</b> {r.reply}</div>}
          </div>
        )) : <div className="empty">No reviews here yet.</div>}
      </div>
    </>
  )
}
