// Sab kuch pehle internet se (naya version turant mile); internet na ho to pichhli copy.
const SHELL = 'ns-shell-v11';
const DATA = 'ns-data-v1';
const SHELL_FILES = ['./', 'index.html', 'app.css', 'app.js', 'manifest.webmanifest', 'icons/icon-192.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const store = url.pathname.includes('/data/') ? DATA : SHELL;
  e.respondWith(fetch(e.request).then((res) => {
    if (res.ok && !url.pathname.endsWith('.pdf')) {
      const copy = res.clone();
      caches.open(store).then((c) => c.put(e.request, copy));
    }
    return res;
  }).catch(() => caches.match(e.request)));
});
