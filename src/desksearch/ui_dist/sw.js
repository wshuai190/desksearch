// DeskSearch Service Worker
const CACHE_NAME = 'desksearch-v1';

// Assets to pre-cache on install
const PRECACHE_URLS = [
  '/',
  '/manifest.json',
  '/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
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

  event.respondWith(
    caches.match(request).then((cached) => {
      // Return cached version if available (cache-first for static assets)
      if (cached) {
        // Refresh cache in background (stale-while-revalidate for JS/CSS)
        if (url.pathname.startsWith('/assets/')) {
          fetch(request).then((response) => {
            if (response.ok) {
              caches.open(CACHE_NAME).then((cache) => cache.put(request, response));
            }
          }).catch(() => {});
        }
        return cached;
      }

      // Network with cache fallback
      return fetch(request).then((response) => {
        if (response.ok && request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => {
        // Offline fallback: serve index.html for navigation requests
        if (request.headers.get('accept')?.includes('text/html')) {
          return caches.match('/') || caches.match('/index.html');
        }
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      });
    })
  );
});
