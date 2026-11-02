import { getLang, t } from "../i18n";
 
export function formatMoney(value) {
    const n = Number(value) || 0;
    return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(n)} ${t("so'm")}`;
}
 
// Bugungi sana, YYYY-MM-DD (kompyuter vaqti bo'yicha)
export function today() {
    const d = new Date();
    const pad = (x) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
 
const MONTHS = [
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];
const MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
// To'liq oy nomi (nomlanish kelishigi): qisqa nomlar (Iyun/Iyul) bilan lug'at kaliti to'qnashmasligi uchun alohida
const monthLabel = (i) => (getLang() === "ru" ? MONTHS_RU[i] : MONTHS[i]);
 
const pad2 = (n) => String(n).padStart(2, "0");
const ddmmyyyy = (date) =>
    `${pad2(date.getUTCDate())}.${pad2(date.getUTCMonth() + 1)}.${date.getUTCFullYear()}`;
 
// kunlik: "07.10.2026" | haftalik: "05.10.2026 – 11.10.2026"
// oylik: "Oktabr 2026" | yillik: "2026"
export function formatPeriod(iso, period) {
    const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
    if (period === "year") return String(y);
    if (period === "month") return `${monthLabel(m - 1)} ${y}`;
 
    const start = new Date(Date.UTC(y, m - 1, d));
    if (period === "week") {
        const end = new Date(Date.UTC(y, m - 1, d + 6));
        return `${ddmmyyyy(start)} – ${ddmmyyyy(end)}`;
    }
    return ddmmyyyy(start);
}
