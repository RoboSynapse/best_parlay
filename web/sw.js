// deploy.yml rewrites VERSION to the commit SHA on every deploy, so phones pick up each new app shell.
const VERSION = 'bp-v4';
const DATA = 'bp-data';  // last good predictions.json, kept across versions
const SHELL = [
  './', 'index.html', 'style.css', 'app.js', 'model.js', 'manifest.webmanifest',
  'icons/icon.svg', 'icons/ui.svg', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png',
  'data/predictions.sample.json',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION && k !== DATA).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;

  if (url.pathname.endsWith('/data/predictions.json')) {
    // Network first: fresh predictions when online, last good copy when offline.
    e.respondWith(fetch(req).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(DATA).then(c => c.put(url.pathname, copy));
      }
      return res;
    }).catch(() => caches.match(url.pathname)
      .then(hit => hit || new Response('offline', { status: 504 }))));
    return;
  }

  // Cache first for the app shell.
  e.respondWith(caches.match(req, { ignoreSearch: true }).then(hit => hit || fetch(req)));
});
