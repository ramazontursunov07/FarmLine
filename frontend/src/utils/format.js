export function formatMoney(value) {
    const n = Number(value) || 0;
    return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(n)} so'm`;
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

// "2026-10-01" -> kunlik: "07.10.2026", oylik: "Oktabr 2026", yillik: "2026"
export function formatPeriod(iso, period) {
    const [y, m, d] = iso.slice(0, 10).split("-");
    if (period === "year") return y;
    if (period === "month") return `${MONTHS[Number(m) - 1]} ${y}`;
    return `${d}.${m}.${y}`;
}
