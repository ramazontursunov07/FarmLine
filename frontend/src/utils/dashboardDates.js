// Dashboard uchun sana va salomlashish yordamchilari
const WEEKDAYS = ['yakshanba', 'dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba'];
const MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];

export function greeting(date = new Date()) {
    const h = date.getHours();
    if (h < 5) return 'Xayrli tun';
    if (h < 12) return 'Xayrli tong';
    if (h < 18) return 'Xayrli kun';
    return 'Xayrli kech';
}

// "payshanba, 15 oktabr"
export function longDate(date = new Date()) {
    return `${WEEKDAYS[date.getDay()]}, ${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

export const monthName = (date = new Date()) => MONTHS[date.getMonth()];

// Necha kun o'tdi (YYYY-MM-DD dan bugungacha), kamida 0
export function daysSince(iso) {
    if (!iso) return 0;
    const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
    const then = new Date(y, m - 1, d);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.max(0, Math.round((today - then) / 86400000));
}
