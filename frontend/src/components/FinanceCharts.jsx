import { useState, useEffect } from 'react';
import api from '../api/axios';
import { formatMoney } from '../utils/format';

const MONTHS_SHORT = ['Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyun', 'Iyul', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek'];
const MONTHS_COUNT = 6;

const CATEGORY_LABELS = {
    ozuqa: 'Ozuqa',
    dori: 'Dori-darmon',
    sotuv: 'Sotuv',
    ish_haqi: 'Ish haqi',
    kommunal: 'Kommunal xarajat',
    boshqa: 'Boshqa',
};

// Pirog bo'laklari ranglari (index.css dagi palitraga mos, bir-biridan ajralib turadi)
const SLICE_COLORS = ['#28402F', '#B8860B', '#5B8C6A', '#B3432F', '#6B7FA3', '#9AA39C'];

const pad = (n) => String(n).padStart(2, '0');

// Oxirgi MONTHS_COUNT oy ro'yxati: [{ key: '2026-10', label: 'Okt' }, ...] (eskidan yangiga)
function lastMonths() {
    const now = new Date();
    const list = [];
    for (let i = MONTHS_COUNT - 1; i >= 0; i--) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        list.push({ key: `${d.getFullYear()}-${pad(d.getMonth() + 1)}`, label: MONTHS_SHORT[d.getMonth()] });
    }
    return list;
}

// 1 250 000 -> "1,3 mln", 45 000 -> "45 ming"
function compact(value) {
    const abs = Math.abs(value);
    const sign = value < 0 ? '−' : '';
    if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1).replace('.', ',')} mlrd`;
    if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(1).replace('.', ',')} mln`;
    if (abs >= 1e3) return `${sign}${Math.round(abs / 1e3)} ming`;
    return `${sign}${Math.round(abs)}`;
}

function ProfitChart({ months }) {
    const W = 360;
    const H = 200;
    const top = 22;
    const bottom = 34;
    const plotH = H - top - bottom;
    const maxPos = Math.max(0, ...months.map((m) => m.profit));
    const maxNeg = Math.max(0, ...months.map((m) => -m.profit));
    const range = maxPos + maxNeg || 1;
    const zeroY = top + (maxPos / range) * plotH;
    const slot = W / months.length;
    const barW = slot * 0.56;

    return (
        <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img"
            aria-label="Oylar bo'yicha foyda va zarar">
            <line x1="0" x2={W} y1={zeroY} y2={zeroY} className="chart-axis" />
            {months.map((m, i) => {
                const h = (Math.abs(m.profit) / range) * plotH;
                const x = i * slot + (slot - barW) / 2;
                const isLoss = m.profit < 0;
                const y = isLoss ? zeroY : zeroY - h;
                const labelY = isLoss ? y + h + 12 : y - 5;
                return (
                    <g key={m.key}>
                        <title>{`${m.label}: ${m.profit >= 0 ? 'foyda' : 'zarar'} ${formatMoney(Math.abs(m.profit))}\nKirim ${formatMoney(m.income)} · Chiqim ${formatMoney(m.expense)}`}</title>
                        <rect x={x} y={y} width={barW} height={Math.max(h, m.profit === 0 ? 0 : 1.5)} rx="3"
                            className={isLoss ? 'chart-bar chart-bar--loss' : 'chart-bar chart-bar--profit'} />
                        {m.profit !== 0 && (
                            <text x={x + barW / 2} y={labelY} textAnchor="middle" className="chart-value">
                                {compact(m.profit)}
                            </text>
                        )}
                        <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="chart-label">{m.label}</text>
                    </g>
                );
            })}
        </svg>
    );
}

function ExpenseDonut({ items, total }) {
    const R = 15.9155; // aylana uzunligi = 100
    let offset = 0;
    return (
        <div className="donut-wrap">
            <svg className="donut-svg" viewBox="0 0 42 42" role="img" aria-label="Chiqimlar kategoriyalar bo'yicha">
                <circle cx="21" cy="21" r={R} className="donut-track" />
                {items.map((it, i) => {
                    const pct = (it.total / total) * 100;
                    const circle = (
                        <circle key={it.category} cx="21" cy="21" r={R} fill="none"
                            stroke={SLICE_COLORS[i % SLICE_COLORS.length]} strokeWidth="6"
                            strokeDasharray={`${pct} ${100 - pct}`} strokeDashoffset={25 - offset}>
                            <title>{`${it.label}: ${formatMoney(it.total)} (${pct.toFixed(1)}%)`}</title>
                        </circle>
                    );
                    offset += pct;
                    return circle;
                })}
                <text x="21" y="20.5" textAnchor="middle" className="donut-total-label">Jami</text>
                <text x="21" y="25.5" textAnchor="middle" className="donut-total">{compact(total)}</text>
            </svg>
            <ul className="donut-legend">
                {items.map((it, i) => (
                    <li key={it.category}>
                        <span className="donut-dot" style={{ background: SLICE_COLORS[i % SLICE_COLORS.length] }} />
                        <span className="donut-name">{it.label}</span>
                        <span className="donut-amount">
                            {formatMoney(it.total)} <em>{((it.total / total) * 100).toFixed(0)}%</em>
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

// farmId: bo'sh bo'lsa barcha fermalar. refreshKey o'zgarsa qayta yuklanadi.
function FinanceCharts({ farmId, refreshKey }) {
    const [months, setMonths] = useState(null);
    const [expenses, setExpenses] = useState(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const list = lastMonths();
        const base = farmId ? { farm: farmId } : {};
        const dateFrom = `${list[0].key}-01`;

        Promise.all([
            api.get('finance/report/', { params: { ...base, period: 'month', date_from: dateFrom } }),
            api.get('finance/summary/', { params: { ...base, transaction_type: 'chiqim', date_from: dateFrom } }),
        ])
            .then(([rep, sum]) => {
                if (cancelled) return;
                const rows = Array.isArray(rep.data) ? rep.data : rep.data.results ?? [];
                const byKey = {};
                rows.forEach((r) => { byKey[r.period.slice(0, 7)] = r; });
                setMonths(list.map((m) => {
                    const r = byKey[m.key];
                    return {
                        ...m,
                        income: Number(r?.income) || 0,
                        expense: Number(r?.expense) || 0,
                        profit: Number(r?.profit) || 0,
                    };
                }));
                setExpenses(
                    (sum.data.by_category || [])
                        .filter((c) => c.transaction_type === 'chiqim')
                        .map((c) => ({
                            category: c.category,
                            label: CATEGORY_LABELS[c.category] || c.category,
                            total: Number(c.total) || 0,
                        }))
                        .filter((c) => c.total > 0)
                        .sort((a, b) => b.total - a.total)
                );
                setFailed(false);
            })
            .catch(() => !cancelled && setFailed(true)); // grafik chiqmasa ham sahifa ishlayveradi
        return () => {
            cancelled = true;
        };
    }, [farmId, refreshKey]);

    // Ruxsat yo'q (masalan moliya huquqisiz) yoki xato: bo'limni yashiramiz
    if (failed || !months) return null;

    const hasData = months.some((m) => m.income || m.expense);
    const expenseTotal = (expenses || []).reduce((s, c) => s + c.total, 0);

    return (
        <div className="charts-grid">
            <section className="overview-box chart-box">
                <h3 className="overview-box-title">Oylik foyda / zarar (oxirgi {MONTHS_COUNT} oy)</h3>
                {hasData ? (
                    <>
                        <ProfitChart months={months} />
                        <p className="chart-legend">
                            <span className="chart-key chart-key--profit" /> Foyda
                            <span className="chart-key chart-key--loss" /> Zarar
                        </p>
                    </>
                ) : (
                    <p className="overview-ok">Hali kirim-chiqim yozuvlari yo'q</p>
                )}
            </section>

            <section className="overview-box chart-box">
                <h3 className="overview-box-title">Eng katta chiqimlar (oxirgi {MONTHS_COUNT} oy)</h3>
                {expenseTotal > 0 ? (
                    <ExpenseDonut items={expenses} total={expenseTotal} />
                ) : (
                    <p className="overview-ok">Hali chiqim yozuvlari yo'q</p>
                )}
            </section>
        </div>
    );
}

export default FinanceCharts;
