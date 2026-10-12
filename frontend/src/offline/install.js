import { useSyncExternalStore } from 'react';

// "Ilovani o'rnatish" tugmasi uchun: brauzer `beforeinstallprompt` hodisasini ilova yuklanishi bilan
// bir marta yuboradi, shuning uchun uni main.jsx da darhol ushlab, shu yerda saqlab turamiz.
let deferredPrompt = null;
let installed = false;
const listeners = new Set();
const emit = () => listeners.forEach((l) => l());

export const isStandalone = () =>
    typeof window !== 'undefined'
    && (window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true);

export function listenForInstall() {
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault(); // brauzerning o'z oynasini emas, bizning tugmani ko'rsatamiz
        deferredPrompt = e;
        emit();
    });
    window.addEventListener('appinstalled', () => {
        deferredPrompt = null;
        installed = true;
        emit();
    });
}

export async function promptInstall() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null; // bir prompt faqat bir marta ishlatiladi
    emit();
}

const subscribe = (l) => {
    listeners.add(l);
    return () => listeners.delete(l);
};

// 'available' - o'rnatish mumkin, tugma ko'rsatiladi
export const useCanInstall = () =>
    useSyncExternalStore(subscribe, () => deferredPrompt !== null && !installed && !isStandalone());
