const CACHE_VERSION = 'velocity-lab-v1.0.0';
const CACHE_FILES = [
    './',
    './index.html',
    './manifest.json',
    'https://cdn.tailwindcss.com',
    'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap'
];

// -----------------------------------------------------------------------------
// INSTALL: CACHE CRITICAL TELEMETRY ASSETS
// -----------------------------------------------------------------------------
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_VERSION)
            .then(cache => cache.addAll(CACHE_FILES))
            .then(() => self.skipWaiting())
    );
});

// -----------------------------------------------------------------------------
// ACTIVATE: CLEANUP OLD VERSIONS
// -----------------------------------------------------------------------------
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.map(key => {
                if (key !== CACHE_VERSION) return caches.delete(key);
            })
        )).then(() => self.clients.claim())
    );
});

// -----------------------------------------------------------------------------
// FETCH: NETWORK-FIRST WITH CACHE FALLBACK (FAIL-SAFE FOR TRACK OPERATION)
// -----------------------------------------------------------------------------
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request)
            .then(response => {
                const clone = response.clone();
                caches.open(CACHE_VERSION).then(cache => cache.put(event.request, clone));
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
