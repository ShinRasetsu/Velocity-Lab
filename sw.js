const CACHE_VERSION = 'velocity-lab-v1.5.0';

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
            .then(cache => cache.addAll(STATIC_ASSETS).catch(() => cache.addAll(['./index.html','./manifest.json'])))
            .then(() => self.skipWaiting())
    );
});

// ─────────────────────────────────────────────
// ACTIVATE
// ─────────────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        (async () => {
            if (self.registration.navigationPreload) {
                try { await self.registration.navigationPreload.enable(); } catch(e) {}
            }
            const keys = await caches.keys();
            await Promise.all(keys.map(k => {
                if (![APP_SHELL_CACHE, RUNTIME_CACHE].includes(k)) return caches.delete(k);
            }));
            await self.clients.claim();
        })()
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
        event.respondWith(appShellStrategy(event));
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

const MAX_RUNTIME = 100;
async function trimCache(cacheName, max) {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length > max) {
        for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
    }
}
async function appShellStrategy(event) {
    const req = event.request;
    const cached = await caches.match(req);
    let preload = null;
    try {
        if (req.mode === 'navigate' && event.preloadResponse) {
            preload = await event.preloadResponse;
        }
    } catch(e) {}
    if (preload) {
        const copy = preload.clone();
        caches.open(APP_SHELL_CACHE).then(c => c.put(req, copy));
        return preload;
    }
    // True stale-while-revalidate: return cached immediately, revalidate in background
    if (cached) {
        fetch(req).then(res => {
            if (res && res.status === 200) {
                const copy = res.clone();
                caches.open(APP_SHELL_CACHE).then(c => c.put(req, copy));
            }
        }).catch(()=>{});
        return cached;
    }
    // No cache — network with 5s timeout
    const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 5000));
    try {
        const res = await Promise.race([fetch(req), timeout]);
        if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(APP_SHELL_CACHE).then(c => c.put(req, copy));
        }
        return res;
    } catch {
        return new Response('Offline', { status: 503, statusText: 'Offline' });
    }
}

async function cacheFirst(req) {
    const cached = await caches.match(req);
    if (cached) return cached;
    try {
        const res = await fetch(req);
        if (res && (res.status === 200 || res.type === 'opaque')) {
            const copy = res.clone();
            const cache = await caches.open(RUNTIME_CACHE);
            await cache.put(req, copy);
            await trimCache(RUNTIME_CACHE, MAX_RUNTIME);
        }
        return res;
    } catch {
        return cached || new Response('Offline', { status: 503 });
    }
}

async function networkFirst(req) {
    try {
        const res = await fetch(req);
        if (res && res.status === 200) {
            const copy = res.clone();
            const cache = await caches.open(RUNTIME_CACHE);
            await cache.put(req, copy);
            await trimCache(RUNTIME_CACHE, MAX_RUNTIME);
        }
        return res;
    } catch {
        const cached = await caches.match(req);
        return cached || new Response('Offline', { status: 503 });
    }
}