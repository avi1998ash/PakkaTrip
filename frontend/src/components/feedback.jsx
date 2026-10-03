import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Icon } from './ui'

const Ctx = createContext(null)

/**
 * Toasts + one modal at a time.
 * modal.open({ title, body, submitLabel, submitClass, cancelLabel, onSubmit(formData) })
 *   body is JSX containing named <input>s; onSubmit gets them as an object. Throwing shows the error in the form.
 */
export function FeedbackProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [modal, setModal] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const seq = useRef(0)
  const formRef = useRef(null)

  const toast = useCallback((msg, isErr = false) => {
    const id = ++seq.current
    setToasts(t => [...t, { id, msg, isErr }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3400)
  }, [])

  const close = useCallback(() => { setModal(null); setError('') }, [])
  const open = useCallback(cfg => { setError(''); setModal({ ...cfg, key: ++seq.current }) }, [])
  const confirm = useCallback((title, message, label, onYes, { cancelLabel = 'Cancel', submitClass = 'btn-danger' } = {}) =>
    open({ title, body: <p className="m-0">{message}</p>, submitLabel: label, submitClass, cancelLabel, onSubmit: onYes }), [open])

  useEffect(() => {
    if (!modal) return
    const onKey = e => { if (e.key === 'Escape') close() }
    document.addEventListener('keydown', onKey)
    setTimeout(() => formRef.current?.querySelector('input:not([type=hidden]),select,textarea')?.focus(), 0)
    return () => document.removeEventListener('keydown', onKey)
  }, [modal, close])

  async function submit(e) {
    e.preventDefault()
    if (!modal.onSubmit) return close()
    const form = e.currentTarget
    if (!form.checkValidity()) { form.reportValidity(); return }
    setBusy(true)
    try {
      const result = await modal.onSubmit(Object.fromEntries(new FormData(form)))
      if (result !== false) close()
    } catch (err) {
      setError(err.message)
      toast(err.message, true)
    } finally { setBusy(false) }
  }

  return (
    <Ctx.Provider value={{ toast, open, close, confirm }}>
      {children}
      {modal && (
        <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-[rgb(11_24_45/.5)]" onMouseDown={e => e.target === e.currentTarget && close()}>
          <div className="bg-white rounded-[14px] w-full max-w-[560px] max-h-[calc(100vh-32px)] flex flex-col shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
            <header className="flex items-center justify-between px-5 py-4 border-b border-line">
              <h3 id="modalTitle" className="text-[17px] font-semibold">{modal.title}</h3>
              <button className="icon-btn" onClick={close} aria-label="Close"><Icon name="x" /></button>
            </header>
            <form key={modal.key} ref={formRef} onSubmit={submit} noValidate className="flex flex-col min-h-0">
              <div className="p-5 overflow-y-auto">
                {error && <div className="form-error" role="alert">{error}</div>}
                {modal.body}
              </div>
              <footer className="flex justify-end gap-2.5 px-5 py-3.5 border-t border-line">
                <button className="btn" type="button" onClick={close}>{modal.onSubmit ? (modal.cancelLabel || 'Cancel') : 'Close'}</button>
                {modal.onSubmit && <button className={`btn ${modal.submitClass || 'btn-primary'}`} type="submit" disabled={busy}>{busy ? 'Saving…' : (modal.submitLabel || 'Save')}</button>}
              </footer>
            </form>
          </div>
        </div>
      )}
      <div className="fixed bottom-5 right-5 left-4 sm:left-auto flex flex-col gap-2 z-[60] items-end" aria-live="polite">
        {toasts.map(t => <div key={t.id} className={`toast ${t.isErr ? 'err' : ''}`}>{t.msg}</div>)}
      </div>
    </Ctx.Provider>
  )
}

export const useFeedback = () => useContext(Ctx)
