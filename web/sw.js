// Service worker: caches ONLY the static page shell (no personal data). Every API/chat/admin request goes straight to the
// network and is never stored, so conversations and health records never enter the browser cache.
const SHELL = "coach-shell-v1", FILES = ["/", "/icon.svg", "/icon-192.png", "/manifest.webmanifest"];
self.addEventListener("install", e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || !FILES.includes(u.pathname)) return;   // everything else: network only
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(SHELL).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request)));   // offline: the empty shell (chat itself needs the server)
});
