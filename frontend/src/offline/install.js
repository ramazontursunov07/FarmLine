// Ilovani telefonga o'rnatish holati. Brauzerning "beforeinstallprompt" hodisasi sahifa yuklanishining
// boshida bir marta keladi, shuning uchun uni React'dan OLDIN (main.jsx'da) ushlab qo'yamiz,
// aks holda keyin ochilgan komponent uni o'tkazib yuboradi.
 
let deferredPrompt = null;
let installedFlag = false;
const listeners = new Set();
 
function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}
 
function isIos() {
    const ua = navigator.userAgent;
    // iPadOS 13+ o'zini Mac deb tanishtiradi, lekin sensorli ekrani bor
    return /iphone|ipad|ipod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}
 
// Telegram, Instagram, Facebook ichida ochilgan sahifada o'rnatish ishlamaydi: oddiy brauzer kerak
function isInAppBrowser() {
    return /Telegram|Instagram|FBAN|FBAV|Line\/|; wv\)/i.test(navigator.userAgent);
}
 
function compute() {
    return {
        canPrompt: Boolean(deferredPrompt),
        installed: installedFlag || isStandalone(),
        ios: isIos(),
        inApp: isInAppBrowser(),
        secure: window.isSecureContext,
    };
}
 
let state = compute();
 
function update() {
    state = compute();
    listeners.forEach((listener) => listener());
}
 
export function initInstallCapture() {
    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault(); // brauzerning o'z oynasi o'rniga o'zimizning tugmani ishlatamiz
        deferredPrompt = event;
        update();
    });
    window.addEventListener('appinstalled', () => {
        deferredPrompt = null;
        installedFlag = true;
        update();
    });
}
 
export function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}
 
export function getSnapshot() {
    return state;
}
 
// 'accepted' | 'dismissed' | 'unavailable' (brauzer bir marta ishlatiladigan hodisa beradi)
export async function promptInstall() {
    if (!deferredPrompt) return 'unavailable';
    const event = deferredPrompt;
    deferredPrompt = null;
    update();
    event.prompt();
    const { outcome } = await event.userChoice;
    return outcome;
}
