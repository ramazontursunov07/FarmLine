// Dashboard uchun sana va salomlashish yordamchilari
import { getLang, t } from '../i18n';

const WEEKDAYS = ['yakshanba', 'dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba'];
const MONTHS_RU_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];

export function greeting(date = new Date()) {
    const h = date.getHours();
    if (h < 5) return t('Xayrli tun');
    if (h < 12) return t('Xayrli tong');
    if (h < 18) return t('Xayrli kun');
    return t('Xayrli kech');
}

// "payshanba, 15 oktabr"
export function longDate(date = new Date()) {
    // Rus tilida sanadagi oy qaratqich kelishigida ("15 октября"), shuning uchun alohida massiv
    const month = getLang() === 'ru' ? MONTHS_RU_GEN[date.getMonth()] : MONTHS[date.getMonth()];
    return `${t(WEEKDAYS[date.getDay()])}, ${date.getDate()} ${month}`;
}

export const monthName = (date = new Date()) => t(MONTHS[date.getMonth()]);

// Necha kun o'tdi (YYYY-MM-DD dan bugungacha), kamida 0
export function daysSince(iso) {
    if (!iso) return 0;
    const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
    const then = new Date(y, m - 1, d);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.max(0, Math.round((today - then) / 86400000));
}
