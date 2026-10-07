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
