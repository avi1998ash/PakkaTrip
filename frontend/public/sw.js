// PakkaTrip service worker. Keeps the app shell fast and shows an offline page; never caches API data,
// so prices, seats, bookings and logins always come live from the server.
const VERSION = 'v1'
const SHELL = `pakkatrip-shell-${VERSION}`
const ASSETS = `pakkatrip-assets-${VERSION}`
const PRECACHE = ['/offline.html', '/icons/public-192.png']

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== SHELL && k !== ASSETS).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', event => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) return

  // Pages: always the latest from the network; the offline page only when there's no connection.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match('/offline.html')))
    return
  }

  // Built JS/CSS has a content hash in its name, so a cached copy never goes stale.
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(
      caches.match(req).then(hit => hit || fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(ASSETS).then(c => c.put(req, copy)) }
        return res
      })),
    )
  }
})
