// Network-first service worker: always uses the live site when online,
// falls back to the last copy it saw when offline (site visits with no signal).
const CACHE = 'site-visit-forms-v2';
const CORE = ['./', 'index.html', 'apple-touch-icon.png', 'data/centers.json', 'data/homes.json'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  const key = url.origin + url.pathname; // ignore cache-busting query strings
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(key, copy)); }
      return res;
    }).catch(() => caches.match(key).then(r => r ||
      (req.mode === 'navigate'
        ? caches.match(new URL('./', self.registration.scope).href).then(r2 => r2 || caches.match(new URL('index.html', self.registration.scope).href)).then(r3 => r3 || Response.error())
        : Response.error())))
  );
});
