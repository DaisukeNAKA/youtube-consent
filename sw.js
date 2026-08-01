// オフライン対策: 3秒だけネットワークを待ち、失敗時はキャッシュへ切り替える。
// Safariがサイトデータを消去した場合は再度オンラインで開く必要がある。
const CACHE = "consent-v2";
const ASSETS = ["./", "./index.html", "./guide.html"];
const NETWORK_TIMEOUT_MS = 3000;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).origin !== location.origin) return;   // GASなどの外部通信はキャッシュしない
  e.respondWith(networkFirst(e.request));
});

async function networkFirst(request) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), NETWORK_TIMEOUT_MS);
  try {
    const response = await fetch(request, { signal: ctrl.signal });
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(request, response.clone());
    }
    return response;
  } catch (_) {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    if (request.mode === "navigate") {
      const app = await caches.match("./index.html");
      if (app) return app;
    }
    return new Response("オフラインのため表示できません。通信できる場所で一度開いてください。", {
      status: 503,
      headers: { "Content-Type": "text/plain;charset=utf-8" }
    });
  } finally {
    clearTimeout(timer);
  }
}
