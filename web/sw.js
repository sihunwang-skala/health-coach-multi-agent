// Service worker: caches ONLY static, non-personal shell files (icons, manifest, design-system CSS/JS). Pages, every API call,
// chat and admin requests go straight to the network and are never stored, so conversations and health records never enter
// the browser cache. Chat itself needs the server, so there is no offline mode.
const SHELL = "coach-shell-v2", FILES = ["/icon.svg", "/icon-192.png", "/icon-512.png", "/manifest.webmanifest", "/ds.css", "/ds.js"];
self.addEventListener("install", e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || !FILES.includes(u.pathname)) return;   // everything else: network only
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(SHELL).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request)));
});
