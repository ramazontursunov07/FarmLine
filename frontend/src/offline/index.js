// FarmLine offline qatlami. axios.js ichida bir marta o'rnatiladi va sahifalarni o'zgartirmasdan ishlaydi:
//
//  1. Har bir muvaffaqiyatli GET javobi telefonga (IndexedDB) saqlanadi. Internet yo'qda shu nusxa ko'rsatiladi.
//  2. Internet yo'qda qilingan yozish amali (POST/PATCH/DELETE) navbatga (outbox) qo'yiladi va foydalanuvchiga
//     "muvaffaqiyatli" deb ko'rsatiladi (ekranda darhol ko'rinadi).
//  3. Internet qaytganda navbat tartib bilan serverga yuboriladi. POST'lar Idempotency-Key bilan ketadi, shuning
//     uchun javob yo'lda yo'qolib qayta yuborilsa ham yozuv ikki marta qo'shilmaydi.

import axios from 'axios';
import { getErrorMessage } from '../utils/errors';
import { idbAll, idbClear, idbCount, idbDelete, idbGet, idbPut } from './idb';
import { applyCreate, applyDelete, applyUpdate, currentUser } from './optimistic';
import { getOfflineState, setOfflineState } from './state';

// Faqat shu resurslarga yozish navbatga qo'yiladi. Login, ro'yxatdan o'tish, parol, Telegram va ishchilar
// (ularda yangi akkaunt yaratiladi) internetni talab qiladi.
const QUEUEABLE = new Set([
    'farms', 'tasks', 'finance', 'animals-event', 'animals-group', 'animals-type',
    'inventory-item', 'inventory-transaction',
]);

const RESOURCE_LABEL = {
    farms: 'Ferma', tasks: 'Vazifa', finance: 'Kirim-chiqim', 'animals-event': 'Hayvon ishi',
    'animals-group': 'Hayvon guruhi', 'animals-type': 'Hayvon turi',
    'inventory-item': 'Ombor mahsuloti', 'inventory-transaction': 'Ombor harakati',
};
const ACTION_LABEL = { post: "qo'shish", patch: "o'zgartirish", delete: "o'chirish" };

const PROBE_INTERVAL_MS = 20000;
const PROBE_TIMEOUT_MS = 6000;

let api = null;

/* ---------- Yordamchilar ---------- */

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}${Math.random().toString(36).slice(2, 8)}`;
// Vaqtinchalik ID manfiy butun son: formalardagi Number(id) ham ishlayveradi va haqiqiy IDlar bilan aralashmaydi
const newTmpId = () => -(Math.floor(Math.random() * 1e9) + 1);

function isOfflineError(error) {
    if (!error || axios.isCancel(error)) return false;
    if (error.isRefreshNetworkError) return true;
    if (!error.response) return true; // tarmoq xatosi yoki timeout
    return [502, 503, 504].includes(error.response.status); // server o'chiq (nginx/proxy javobi)
}

// 'finance/' -> { resource: 'finance', id: null }, 'tasks/5/' -> { resource: 'tasks', id: 5 }
function parseUrl(url, baseURL = '') {
    let clean = String(url || '');
    if (baseURL && clean.startsWith(baseURL)) clean = clean.slice(baseURL.length);
    clean = clean.replace(/^\/+/, '').split('?')[0];
    const m = clean.match(/^([a-z-]+)\/(?:(-?\d+)\/)?$/);
    return { path: clean, resource: m?.[1] ?? null, id: m?.[2] != null ? Number(m[2]) : null };
}

function parseBody(data) {
    if (data == null || data === '') return null;
    if (typeof data === 'string') {
        try {
            return JSON.parse(data);
        } catch {
            return null;
        }
    }
    return data;
}

const fakeResponse = (config, data, status = 200, extra = {}) => ({
    data, status, statusText: 'OK (offline)', headers: {}, config, request: null, ...extra,
});

/* ---------- Holat ---------- */

async function refreshCounts() {
    const user = currentUser();
    if (!user) return setOfflineState({ pending: 0, failed: [] });
    try {
        const [outbox, failed] = await Promise.all([idbAll('outbox'), idbAll('failed')]);
        setOfflineState({
            pending: outbox.filter((o) => o.userId === user.id).length,
            failed: failed.filter((o) => o.userId === user.id).sort((a, b) => a.seq - b.seq),
        });
    } catch {
        /* IndexedDB yo'q: navbat ishlamaydi */
    }
}

function markOnline() {
    if (getOfflineState().offline) setOfflineState({ offline: false });
    if (getOfflineState().pending > 0) syncNow();
}

const markOffline = () => setOfflineState({ offline: true });

/* ---------- GET keshi ---------- */

async function cacheGet(config) {
    const user = currentUser();
    if (!user) return null;
    try {
        return await idbGet('cache', `${user.id}|${api.getUri(config)}`);
    } catch {
        return null;
    }
}

function cachePut(response) {
    const user = currentUser();
    const { config } = response;
    if (!user || !config) return;
    const { path } = parseUrl(config.url, config.baseURL);
    idbPut('cache', {
        key: `${user.id}|${api.getUri(config)}`,
        path,
        params: config.params || {},
        data: response.data,
        ts: Date.now(),
    }).catch(() => {});
}

/* ---------- Yozishni navbatga qo'yish ---------- */

async function enqueue(config) {
    const user = currentUser();
    const method = (config.method || '').toLowerCase();
    const { resource, id, path } = parseUrl(config.url, config.baseURL);
    if (!user || !resource || !QUEUEABLE.has(resource)) return null;
    if (method === 'post' && id != null) return null;
    if ((method === 'patch' || method === 'put') && id == null) return null;
    if (method === 'delete' && id == null) return null;
    if (!['post', 'patch', 'put', 'delete'].includes(method)) return null;

    const body = parseBody(config.data);
    const normalizedMethod = method === 'put' ? 'patch' : method;
    const outbox = (await idbAll('outbox')).filter((o) => o.userId === user.id);

    // Hali yuborilmagan (vaqtinchalik ID'li) yozuvga tegishli o'zgarish: alohida so'rov kerak emas
    if (id != null && id < 0) {
        const creator = outbox.find((o) => o.tmpId === id);
        if (creator) {
            if (normalizedMethod === 'patch') {
                await idbPut('outbox', { ...creator, data: { ...creator.data, ...body } });
                const rec = await applyUpdate(user.id, resource, id, body || {});
                await refreshCounts();
                return fakeResponse(config, rec, 200, { offlineQueued: true });
            }
            // O'chirish: yaratish so'rovi ham, unga bog'liq boshqa so'rovlar ham kerak emas
            for (const o of outbox) {
                if (o.seq === creator.seq || JSON.stringify([o.url, o.data]).includes(String(id))) {
                    await idbDelete('outbox', o.seq);
                }
            }
            await applyDelete(user.id, resource, id);
            await refreshCounts();
            return fakeResponse(config, '', 204, { offlineQueued: true });
        }
    }

    const op = {
        userId: user.id,
        method: normalizedMethod,
        url: path,
        params: config.params || undefined,
        data: body,
        key: config.headers?.get?.('Idempotency-Key') || uid(),
        resource,
        createdAt: Date.now(),
    };

    let data;
    if (normalizedMethod === 'post') {
        op.tmpId = newTmpId();
        data = await applyCreate(user.id, resource, body || {}, op.tmpId); // tekshiruv xatosi bo'lsa shu yerda uzatiladi
    } else if (normalizedMethod === 'patch') {
        data = await applyUpdate(user.id, resource, id, body || {});
    } else {
        await applyDelete(user.id, resource, id);
        data = '';
    }
    await idbPut('outbox', op);
    await refreshCounts();
    return fakeResponse(config, data, normalizedMethod === 'post' ? 201 : normalizedMethod === 'delete' ? 204 : 200, {
        offlineQueued: true,
    });
}

/* ---------- Sinxronlash ---------- */

let flushing = false;

async function loadIdMap() {
    return (await idbGet('meta', 'idMap'))?.map ?? {};
}

const saveIdMap = (map) => idbPut('meta', { key: 'idMap', map });

function substitute(value, map) {
    if (typeof value === 'number') return map[value] ?? value;
    if (Array.isArray(value)) return value.map((v) => substitute(v, map));
    if (value && typeof value === 'object') {
        return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, substitute(v, map)]));
    }
    return value;
}

const substituteUrl = (url, map) => url.replace(/\/(-\d+)\//g, (m, n) => (map[n] != null ? `/${map[n]}/` : m));

function containsTmp(value, tmpIds) {
    if (typeof value === 'number') return tmpIds.has(value);
    if (Array.isArray(value)) return value.some((v) => containsTmp(v, tmpIds));
    if (value && typeof value === 'object') return Object.values(value).some((v) => containsTmp(v, tmpIds));
    return false;
}

export function describeOp(op) {
    const name = RESOURCE_LABEL[op.resource] || op.resource;
    const d = op.data || {};
    const detail = d.title || d.item_name || d.name || d.description || d.note || (d.amount ? `${d.amount} so'm` : '');
    return `${name}: ${ACTION_LABEL[op.method] || op.method}${detail ? ` («${String(detail).slice(0, 40)}»)` : ''}`;
}

export async function syncNow() {
    if (flushing || !api) return;
    const user = currentUser();
    if (!user || !localStorage.getItem('access')) return;

    flushing = true;
    setOfflineState({ syncing: true });
    let changed = 0;
    let reachedServer = false;

    try {
        const map = await loadIdMap();
        const ops = (await idbAll('outbox')).filter((o) => o.userId === user.id).sort((a, b) => a.seq - b.seq);
        // Hali haqiqiy ID olmagan vaqtinchalik IDlar: ularga tayanadigan so'rovlar yuborilmaydi
        const unresolved = new Set(ops.filter((o) => o.tmpId).map((o) => o.tmpId));

        for (const op of ops) {
            const url = substituteUrl(op.url, map);
            const data = substitute(op.data, map);
            const failWith = async (message) => {
                await idbPut('failed', { ...op, message });
                await idbDelete('outbox', op.seq);
                changed += 1;
            };

            if (containsTmp(data, unresolved) || /\/-\d+\//.test(url)) {
                await failWith("Oldingi o'zgarish yuborilmagani uchun bu ham yuborilmadi");
                continue;
            }

            try {
                const res = await api.request({
                    method: op.method, url, params: op.params, data,
                    headers: op.method === 'post' ? { 'Idempotency-Key': op.key } : undefined,
                    _replay: true,
                });
                reachedServer = true;
                if (op.tmpId != null) {
                    unresolved.delete(op.tmpId);
                    if (res.data?.id != null) {
                        map[op.tmpId] = res.data.id;
                        await saveIdMap(map);
                    }
                }
                await idbDelete('outbox', op.seq);
                changed += 1;
            } catch (err) {
                if (isOfflineError(err)) {
                    markOffline();
                    break; // internet yana yo'qoldi: qolganlari keyingi safar
                }
                reachedServer = true;
                if (op.method === 'delete' && err.response?.status === 404) {
                    await idbDelete('outbox', op.seq); // allaqachon o'chirilgan
                    changed += 1;
                } else if (err.response?.status === 401) {
                    break; // sessiya tugagan: foydalanuvchi qayta kirgach davom etadi
                } else {
                    // tmpId "unresolved" da qoladi: unga tayanadigan keyingi so'rovlar yuqoridagi tekshiruvda rad etiladi
                    await failWith(getErrorMessage(err, "Server qabul qilmadi"));
                }
            }
        }
    } catch {
        /* IndexedDB xatosi: keyingi urinishda qayta */
    } finally {
        flushing = false;
        await refreshCounts();
        setOfflineState({
            syncing: false,
            ...(reachedServer ? { offline: false } : {}),
            ...(changed ? { syncVersion: getOfflineState().syncVersion + 1 } : {}),
        });
    }
}

export async function discardFailed(seq) {
    await idbDelete('failed', seq);
    await refreshCounts();
    setOfflineState({ syncVersion: getOfflineState().syncVersion + 1 }); // sahifalar serverdagi haqiqiy holatni qayta oladi
}

/* ---------- Server bilan aloqani tekshirish ---------- */

async function probe() {
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
        // no-cors: javob o'qilmaydi, lekin server bilan aloqa borligini bildiradi (boshqa domen bo'lsa ham)
        await fetch(api.defaults.baseURL || '/api/', { method: 'GET', mode: 'no-cors', cache: 'no-store', signal: controller.signal });
        clearTimeout(timer);
        return true;
    } catch {
        return false;
    }
}

async function checkConnection() {
    const s = getOfflineState();
    if (!s.offline && s.pending === 0) return;
    if (await probe()) {
        setOfflineState({ offline: false });
        syncNow();
    } else if (!s.offline) {
        markOffline();
    }
}

/* ---------- Sessiya tugaganda ---------- */

// Chiqishda telefondagi ma'lumot nusxasi o'chiriladi (umumiy telefonda boshqa odam ko'rmasligi uchun).
// Yuborilmagan o'zgarishlar (outbox) saqlanadi: o'sha foydalanuvchi qayta kirsa, ular yuboriladi.
export async function clearOfflineCache() {
    try {
        await idbClear('cache');
    } catch {
        /* ahamiyatsiz */
    }
    refreshCounts();
}

export async function pendingCount() {
    try {
        return await idbCount('outbox');
    } catch {
        return 0;
    }
}

/* ---------- O'rnatish ---------- */

export function installOffline(instance) {
    api = instance;

    // POST so'roviga Idempotency-Key qo'yamiz: birinchi urinish ham, navbatdan qayta yuborish ham bir xil kalit bilan ketadi
    api.interceptors.request.use((config) => {
        const { resource, id } = parseUrl(config.url, config.baseURL);
        if ((config.method || '').toLowerCase() === 'post' && id == null && QUEUEABLE.has(resource)
            && !config.headers.get('Idempotency-Key')) {
            config.headers.set('Idempotency-Key', uid());
        }
        return config;
    });

    api.interceptors.response.use(
        (response) => {
            if ((response.config?.method || '').toLowerCase() === 'get') cachePut(response);
            markOnline();
            return response;
        },
        async (error) => {
            const config = error?.config;
            if (!config || config._replay || !isOfflineError(error)) {
                if (error?.response) markOnline(); // server javob berdi (masalan 400): internet bor
                return Promise.reject(error);
            }

            markOffline();
            const method = (config.method || 'get').toLowerCase();

            if (method === 'get') {
                const entry = await cacheGet(config);
                if (entry) return fakeResponse(config, entry.data, 200, { fromCache: true, cachedAt: entry.ts });
                return Promise.reject(error);
            }

            try {
                const queued = await enqueue(config);
                if (queued) return queued;
            } catch (localError) {
                if (localError?.data) {
                    // Mahalliy tekshiruv (masalan, omborda yetarli emas): server xatosi kabi ko'rsatamiz
                    return Promise.reject(new axios.AxiosError(
                        localError.message, axios.AxiosError.ERR_BAD_REQUEST, config, null,
                        { status: 400, statusText: 'Bad Request', data: localError.data, headers: {}, config },
                    ));
                }
            }
            return Promise.reject(error);
        },
    );

    if (typeof window === 'undefined') return;

    window.addEventListener('online', checkConnection);
    window.addEventListener('offline', markOffline);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            refreshCounts();
            checkConnection();
            if (getOfflineState().pending > 0) syncNow();
        }
    });
    setInterval(checkConnection, PROBE_INTERVAL_MS);

    refreshCounts().then(() => {
        if (getOfflineState().pending > 0) syncNow();
    });
}
