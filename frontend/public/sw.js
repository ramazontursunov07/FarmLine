/*
 * FarmLine service worker.
 * Ilova "qobig'ini" (HTML, JS, CSS, shriftlar, ikonkalar) telefonda saqlaydi, shuning uchun ilova
 * internet yo'q joyda ham ochiladi. Ma'lumotlar (/api) bu yerda saqlanmaydi va hech qachon ushlanmaydi.
 *
 * Yangi versiyada keshni to'liq yangilash kerak bo'lsa, VERSION ni o'zgartiring.
 */
const VERSION = 'v1';
const CACHE = `farmline-${VERSION}`;
const FONT_CACHE = 'farmline-fonts';
const SHELL = '/index.html';
// Server javobida "Vary: Origin" bo'lishi mumkin: JS/CSS so'rovida Origin sarlavhasi bor, kesh yozuvida yo'q va
// kesh "mos kelmadi" deb internetga chiqib ketadi (offline'da ilova bo'sh qoladi). Shuning uchun Vary e'tiborsiz.
const MATCH = { ignoreVary: true };
const NAV_TIMEOUT_MS = 4000; // sust tarmoqda sahifani uzoq kutmaymiz, telefondagi nusxani ochamiz
const STATIC_FILES = [
    '/manifest.webmanifest',
    '/favicon.svg',
    '/icons/icon-192.png',
    '/icons/icon-512.png',
    '/icons/apple-touch-icon.png',
];
// Bu manzillarga tegmaymiz: API va Django'ning o'z sahifalari
const SKIP_PREFIXES = ['/api/', '/admin/', '/static/', '/media/'];

self.addEventListener('install', (event) => {
    event.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        (async () => {
            const names = await caches.keys();
            await Promise.all(
                names
                    .filter((n) => n.startsWith('farmline-') && n !== CACHE && n !== FONT_CACHE)
                    .map((n) => caches.delete(n))
            );
            await self.clients.claim();
        })()
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);

    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
        event.respondWith(staleWhileRevalidate(event, FONT_CACHE));
        return;
    }
    if (url.origin !== self.location.origin) return;
    if (SKIP_PREFIXES.some((p) => url.pathname.startsWith(p))) return;

    if (request.mode === 'navigate') {
        event.respondWith(handleNavigation(event));
    } else if (url.pathname.startsWith('/assets/')) {
        event.respondWith(cacheFirst(request)); // fayl nomida hash bor: mazmuni o'zgarmaydi
    } else {
        event.respondWith(staleWhileRevalidate(event, CACHE));
    }
});

async function precache() {
    const cache = await caches.open(CACHE);
    const response = await fetch('/', { cache: 'reload' });
    if (!response.ok) throw new Error("Ilova qobig'ini yuklab bo'lmadi");
    await storeShell(cache, response);
    await cache.addAll(STATIC_FILES);
}

// index.html ni va u ishlatadigan hamma fayllarni (JS, CSS, CSS ichidagi shriftlar) saqlaydi
async function storeShell(cache, response) {
    const html = await response.clone().text();
    await cache.put(SHELL, response);

    const assets = new Set();
    for (const m of html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g)) assets.add(m[1]);
    await addMissing(cache, assets);

    // CSS ichidagi url(...) (shrift, rasm) ham kerak
    for (const cssPath of [...assets].filter((u) => u.endsWith('.css'))) {
        const cssResponse = await cache.match(cssPath, MATCH);
        if (!cssResponse) continue;
        const css = await cssResponse.text();
        const base = new URL(cssPath, self.location.origin);
        for (const m of css.matchAll(/url\(\s*["']?([^"')]+?)["']?\s*\)/g)) {
            if (m[1].startsWith('data:')) continue;
            const target = new URL(m[1], base);
            if (target.origin === self.location.origin) assets.add(target.pathname);
        }
    }
    await addMissing(cache, assets);

    // Endi ishlatilmaydigan eski fayllarni o'chiramiz, kesh to'lib ketmasin
    const keep = new Set([...assets].map((u) => new URL(u, self.location.origin).href));
    for (const req of await cache.keys()) {
        const u = new URL(req.url);
        if (u.pathname.startsWith('/assets/') && !keep.has(u.href)) await cache.delete(req);
    }
}

async function addMissing(cache, paths) {
    await Promise.all(
        [...paths].map(async (p) => {
            if (!(await cache.match(p, MATCH))) await cache.add(p);
        })
    );
}

async function handleNavigation(event) {
    const cache = await caches.open(CACHE);
    try {
        const response = await Promise.race([
            fetch(event.request),
            new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), NAV_TIMEOUT_MS)),
        ]);
        if (response.ok && (response.headers.get('content-type') || '').includes('text/html')) {
            // Eng yangi qobiqni orqa fonda saqlab qo'yamiz
            event.waitUntil(storeShell(cache, response.clone()).catch(() => {}));
        }
        return response;
    } catch {
        // Internet yo'q yoki juda sust: ilova qobig'ini telefondan ochamiz (React o'zi to'g'ri sahifani chizadi)
        return (await cache.match(SHELL, MATCH)) || Response.error();
    }
}

async function cacheFirst(request) {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(request, MATCH);
    if (hit) return hit;
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
}

async function staleWhileRevalidate(event, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(event.request, MATCH);
    const network = fetch(event.request)
        .then((response) => {
            // opaque: boshqa domendan (Google Fonts) kelgan javob, uni ham saqlaymiz
            if (response.ok || response.type === 'opaque') cache.put(event.request, response.clone());
            return response;
        })
        .catch(() => undefined);
    event.waitUntil(network);
    return cached || (await network) || Response.error();
}
