// DeskSearch Service Worker
// IMPORTANT: bump this version on every release so stale HTML/assets are purged
const CACHE_NAME = 'desksearch-v0.6.3';

// Assets to pre-cache on install
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/icon.svg',
];

self.addEventListener('install', (event) => {
  // Force the new SW to activate immediately (don't wait for old tabs to close)
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  // Delete ALL old caches so stale index.html / assets are purged
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never intercept API or WebSocket calls — always go to network
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    return;
  }

  // For non-GET requests, skip caching
  if (request.method !== 'GET') {
    return;
  }

  // HTML pages: network-first (always get fresh HTML to pick up new asset hashes)
  const isNavigation = request.headers.get('accept')?.includes('text/html')
    || url.pathname === '/';

  if (isNavigation) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => {
        return caches.match('/') || new Response('Offline', { status: 503 });
      })
    );
    return;
  }

  // Static assets (JS/CSS with hashed filenames): cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => {
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      });
    })
  );
});
