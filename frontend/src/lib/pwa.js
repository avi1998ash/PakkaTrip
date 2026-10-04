import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// Two installable apps from one site: "PakkaTrip" for travellers and "PakkaTrip Partner" for operators/admins.
const APPS = {
  public: { manifest: '/manifest-public.webmanifest', icon: '/icons/public-192.png', apple: '/icons/public-apple-180.png', title: 'PakkaTrip' },
  partner: { manifest: '/manifest-partner.webmanifest', icon: '/icons/partner-192.png', apple: '/icons/partner-apple-180.png', title: 'PT Partner' },
}

export const isPartnerPath = path => /^\/(partner|operator|admin)(\/|$)/.test(path)

function setAttr(id, attr, value) {
  const el = document.getElementById(id)
  if (el && el.getAttribute(attr) !== value) el.setAttribute(attr, value)
}

// Keeps the manifest and icons matching the current page as the user moves between the traveller site and partner portal.
export function useAppManifest() {
  const { pathname } = useLocation()
  useEffect(() => {
    const app = APPS[isPartnerPath(pathname) ? 'partner' : 'public']
    setAttr('app-manifest', 'href', app.manifest)
    setAttr('app-icon', 'href', app.icon)
    setAttr('app-apple-icon', 'href', app.apple)
    setAttr('app-title', 'content', app.title)
  }, [pathname])
}

export function registerServiceWorker() {
  // Needs a secure context (https or localhost); on plain http over Wi-Fi the browser hides serviceWorker.
  if (!('serviceWorker' in navigator)) return
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { /* app still works without it */ })
  })
}
