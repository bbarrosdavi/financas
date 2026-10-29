// Guarda só a casca do site para abrir rápido; dado sempre vem da rede.
const CASCA = 'financas-v19';
const ARQS = ['/', '/index.html', '/style.css', '/app.js', '/vendor/muuri.min.js', '/manifest.webmanifest', '/icone-192.png', '/icone.png'];
self.addEventListener('install', e => e.waitUntil(caches.open(CASCA).then(c => c.addAll(ARQS))));
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CASCA).map(k => caches.delete(k))))));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.pathname.startsWith('/api/') || e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(CASCA).then(k => k.put(e.request, c)); return r; })
    .catch(() => caches.match(e.request)));
});
