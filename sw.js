const CACHE_VERSION = 'velocity-lab-v1.4.0';

const APP_SHELL_CACHE = `shell-${CACHE_VERSION}`;
const RUNTIME_CACHE   = `runtime-${CACHE_VERSION}`;

const STATIC_ASSETS = [
    './',
    './index.html',
    './manifest.json',
    './icon-192.png',
    './icon-512.png',
    './icon-maskable-512.png',
    './apple-touch-icon.png'
];

// ─────────────────────────────────────────────
// INSTALL
// ─────────────────────────────────────────────
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(APP_SHELL_CACHE)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// ─────────────────────────────────────────────
// ACTIVATE
// ─────────────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.map(k => {
                    if (![APP_SHELL_CACHE, RUNTIME_CACHE].includes(k)) {
                        return caches.delete(k);
                    }
                })
            )
        ).then(() => self.clients.claim())
    );
});

// ─────────────────────────────────────────────
// FETCH STRATEGY ENGINE
// ─────────────────────────────────────────────
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // ── APP SHELL (fastest offline boot)
    if (url.origin === self.location.origin) {
        event.respondWith(appShellStrategy(event.request));
        return;
    }

    // ── CDN (Tailwind + Fonts)
    if (
        url.hostname.includes('fonts.googleapis.com') ||
        url.hostname.includes('fonts.gstatic.com')
    ) {
        event.respondWith(cacheFirst(event.request));
        return;
    }

    // ── EVERYTHING ELSE
    event.respondWith(networkFirst(event.request));
});

// ─────────────────────────────────────────────
// STRATEGIES
// ─────────────────────────────────────────────

async function appShellStrategy(req) {
    const cached = await caches.match(req);
    const networkPromise = fetch(req).then(res => {
        if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(APP_SHELL_CACHE).then(c => c.put(req, copy));
        }
        return res;
    }).catch(() => null);

    return cached || networkPromise;
}

async function cacheFirst(req) {
    const cached = await caches.match(req);
    if (cached) return cached;

    try {
        const res = await fetch(req);
        if (res && (res.status === 200 || res.type === 'opaque')) {
            const copy = res.clone();
            const cache = await caches.open(RUNTIME_CACHE);
            cache.put(req, copy);
        }
        return res;
    } catch {
        return cached;
    }
}

async function networkFirst(req) {
    try {
        const res = await fetch(req);
        if (res && res.status === 200) {
            const copy = res.clone();
            const cache = await caches.open(RUNTIME_CACHE);
            cache.put(req, copy);
        }
        return res;
    } catch {
        return caches.match(req);
    }
}