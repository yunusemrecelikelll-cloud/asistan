// NOVA servis çalışanı.
// Yalnızca kabuğu (HTML/CSS/JS) önbelleğe alır; API istekleri her zaman ağdan
// gider — proje durumu ve komut sonuçları taze olmak zorunda.

const SURUM = 'nova-v2';
const KABUK = ['/', '/manifest.json'];
// CSS ve JS kabuğa alınmıyor: adreslerinde sürüm damgası var, zaten
// değiştiklerinde yeni adresten iniyorlar. Önbelleğe almak eski sürümün
// takılı kalmasına yol açıyordu.

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(SURUM).then((c) => c.addAll(KABUK)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((adlar) => Promise.all(adlar.filter((a) => a !== SURUM).map((a) => caches.delete(a))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then((y) => {
        if (y.ok) {
          const kopya = y.clone();
          caches.open(SURUM).then((c) => c.put(e.request, kopya));
        }
        return y;
      })
      .catch(() => caches.match(e.request).then((y) => y || caches.match('/')))
  );
});
