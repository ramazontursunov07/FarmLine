import { useSyncExternalStore } from 'react';

// Offline holati: butun ilova shuni kuzatadi (banner, sinxronlashdan keyin sahifalarni yangilash).
// offline      - internet yo'q (yoki server javob bermayapti)
// pending      - serverga hali yuborilmagan o'zgarishlar soni
// failed       - server rad etgan o'zgarishlar (foydalanuvchi ko'rib chiqishi kerak)
// syncing      - hozir yuborilmoqda
// syncVersion  - har safar navbatdan kamida bitta o'zgarish yuborilganda oshadi: sahifalar yangi ma'lumot oladi
let state = {
    offline: typeof navigator !== 'undefined' && navigator.onLine === false,
    pending: 0,
    failed: [],
    syncing: false,
    syncVersion: 0,
};

const listeners = new Set();

export const getOfflineState = () => state;

export function setOfflineState(patch) {
    const next = { ...state, ...patch };
    if (Object.keys(patch).every((k) => Object.is(state[k], next[k]))) return;
    state = next;
    listeners.forEach((l) => l());
}

function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export const useOfflineState = () => useSyncExternalStore(subscribe, getOfflineState);
