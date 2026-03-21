// FireForm Field — Service Worker v2
// Strategy: Cache-first for app shell, network-only for API

const CACHE = 'fireform-field-v2';

// Everything needed to run the app offline
const SHELL = [
  '/mobile/',
  '/mobile/index.html',
  '/mobile/manifest.json',
];

// Install — cache app shell immediately
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => {
      return cache.addAll(SHELL);
    }).then(() => self.skipWaiting())
  );
});

// Activate — delete old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch strategy:
// - API calls (/forms, /templates, /transcribe) → network only, fail silently
// - App shell → cache first, fallback to network, always update cache
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API calls — always try network, never cache
  if (url.pathname.startsWith('/forms') ||
      url.pathname.startsWith('/templates') ||
      url.pathname.startsWith('/transcribe')) {
    e.respondWith(
      fetch(e.request).catch(() => 
        new Response(JSON.stringify({detail: 'Offline — station unreachable'}), {
          status: 503,
          headers: {'Content-Type': 'application/json'}
        })
      )
    );
    return;
  }

  // App shell — cache first
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) {
        // Serve from cache immediately, update in background
        fetch(e.request).then(response => {
          if (response && response.ok) {
            caches.open(CACHE).then(cache => cache.put(e.request, response));
          }
        }).catch(() => {});
        return cached;
      }
      // Not in cache — try network
      return fetch(e.request).then(response => {
        if (response && response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(cache => cache.put(e.request, clone));
        }
        return response;
      }).catch(() => {
        // Complete offline fallback
        return caches.match('/mobile/index.html');
      });
    })
  );
});