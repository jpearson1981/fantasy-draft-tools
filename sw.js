// Offline cache for the draft tools. Bump VERSION when files change to force a refresh.
const VERSION = "v1";
const CACHE = "ff-tools-" + VERSION;
const CORE = [
  "./", "index.html", "dynasty.html", "lone-rangers.html", "work-league.html",
  "dynasty.webmanifest", "lone-rangers.webmanifest", "work-league.webmanifest", "hub.webmanifest",
  "https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"
];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(
    CORE.map((u) => c.add(new Request(u, { mode: u.startsWith("http") ? "cors" : "same-origin" })).catch(() => {})))
  ).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
// Network-first for our own pages (so updates arrive), cache-first for CDN libraries.
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    e.respondWith(fetch(req).then((r) => {
      const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return r;
    }).catch(() => caches.match(req).then((m) => m || caches.match("index.html"))));
  } else if (url.hostname === "cdnjs.cloudflare.com") {
    e.respondWith(caches.match(req).then((m) => m || fetch(req).then((r) => {
      const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return r;
    })));
  }
});
