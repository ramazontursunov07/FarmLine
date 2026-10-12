// IndexedDB ustidagi kichik va'dali (promise) qobiq. Qo'shimcha kutubxona kerak emas.
// Brauzer IndexedDB'ni bermasa (masalan, ba'zi maxfiy rejimlar), hamma funksiya xatoga tushadi va
// chaqiruvchi ilovani offline imkoniyatsiz, oddiy rejimda ishlatishda davom etadi.

const DB_NAME = 'farmline-offline';
const DB_VERSION = 1;

// cache  - GET javoblarining nusxasi (internet yo'qda shundan o'qiladi)
// outbox - internet yo'qda qilingan, hali serverga yuborilmagan o'zgarishlar (navbat)
// failed - serverga yuborilganda rad etilgan o'zgarishlar (foydalanuvchi ko'rib chiqadi)
// meta   - vaqtinchalik ID -> haqiqiy ID xaritasi
const STORES = {
    cache: { keyPath: 'key' },
    outbox: { keyPath: 'seq', autoIncrement: true },
    failed: { keyPath: 'seq' },
    meta: { keyPath: 'key' },
};

let dbPromise = null;

function open() {
    if (!dbPromise) {
        dbPromise = new Promise((resolve, reject) => {
            if (typeof indexedDB === 'undefined') return reject(new Error('IndexedDB yo\'q'));
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = () => {
                for (const [name, opts] of Object.entries(STORES)) {
                    if (!req.result.objectStoreNames.contains(name)) req.result.createObjectStore(name, opts);
                }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
        dbPromise.catch(() => {
            dbPromise = null;
        });
    }
    return dbPromise;
}

// fn(store) IDBRequest qaytarsa, uning natijasi qaytariladi
async function run(storeName, mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
        const t = db.transaction(storeName, mode);
        let result;
        const request = fn(t.objectStore(storeName));
        if (request) request.onsuccess = () => (result = request.result);
        t.oncomplete = () => resolve(result);
        t.onerror = () => reject(t.error);
        t.onabort = () => reject(t.error);
    });
}

export const idbGet = (store, key) => run(store, 'readonly', (s) => s.get(key));
export const idbPut = (store, value) => run(store, 'readwrite', (s) => s.put(value));
export const idbDelete = (store, key) => run(store, 'readwrite', (s) => s.delete(key));
export const idbAll = (store) => run(store, 'readonly', (s) => s.getAll());
export const idbCount = (store) => run(store, 'readonly', (s) => s.count());
export const idbClear = (store) => run(store, 'readwrite', (s) => s.clear());
