const CACHE_VERSION = 'velocity-lab-v1.0.0';

// LOCAL ASSETS ONLY — CDN URLs must never be in addAll().
// If any URL in addAll() fails, the entire SW install aborts silently.
// CDN resources are cached opportunistically on first fetch instead.
const STATIC_ASSETS = [
    './',
    './index.html',
    './manifest.json'
];

// -----------------------------------------------------------------------------
// INSTALL: CACHE ONLY GUARANTEED LOCAL ASSETS
// -----------------------------------------------------------------------------
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_VERSION)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// -----------------------------------------------------------------------------
// ACTIVATE: CLEANUP OLD VERSIONS
// -----------------------------------------------------------------------------
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.map(key => key !== CACHE_VERSION ? caches.delete(key) : null)
            ))
            .then(() => self.clients.claim())
    );
});

// -----------------------------------------------------------------------------
// FETCH: STRATEGY SPLIT BY RESOURCE TYPE
// -----------------------------------------------------------------------------
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;
    if (!event.request.url.startsWith('http')) return; // Skip chrome-extension:// etc.

    const url = new URL(event.request.url);

    // APP SHELL: Cache-first → guarantees offline boot at track with no signal
    if (url.origin === self.location.origin) {
        event.respondWith(
            caches.match(event.request).then(cached => {
                const networkFetch = fetch(event.request).then(res => {
                    if (res && res.status === 200) {
                        caches.open(CACHE_VERSION).then(c => c.put(event.request, res.clone()));
                    }
                    return res;
                });
                // Serve from cache instantly, update in background
                return cached || networkFetch;
            })
        );
        return;
    }

    // CDN ASSETS (Tailwind, Google Fonts): Cache-first, silent background update
    if (url.hostname.includes('cdn.tailwindcss.com') ||
        url.hostname.includes('fonts.googleapis.com') ||
        url.hostname.includes('fonts.gstatic.com')) {
        event.respondWith(
            caches.match(event.request).then(cached => {
                const networkFetch = fetch(event.request).then(res => {
                    // Cache opaque (cross-origin no-cors) and clean 200s only
                    if (res && (res.status === 200 || res.type === 'opaque')) {
                        caches.open(CACHE_VERSION).then(c => c.put(event.request, res.clone()));
                    }
                    return res;
                }).catch(() => null);
                return cached || networkFetch;
            })
        );
        return;
    }

    // ALL OTHER REQUESTS: Network-first, cache fallback
    event.respondWith(
        fetch(event.request)
            .then(res => {
                if (res && res.status === 200) {
                    caches.open(CACHE_VERSION).then(c => c.put(event.request, res.clone()));
                }
                return res;
            })
            .catch(() => caches.match(event.request))
    );
});