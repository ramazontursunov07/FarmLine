import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatMoney, formatPeriod, today } from '../utils/format';

const num = (n) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const money = (v) => (v === null || v === undefined ? '—' : formatMoney(v));
const profitClass = (v) => (v === null || v === undefined ? '' : Number(v) < 0 ? 'amount-out' : 'amount-in');

const VERDICTS = {
    foyda: { label: 'Foyda', cls: 'work-badge--preg' },
    zarar: { label: 'Zarar', cls: 'work-badge--shoshilinch' },
    sut_yoq: { label: 'Sut bermayapti', cls: 'work-badge--shoshilinch' },
    narx_yoq: { label: 'Narx yo\'q', cls: '' },
};

// 1 litr sut tannarxi va har bir sigirning foyda/zarari: sotiladigan sigirni tanlash uchun.
function MilkProfit({ farmId, refreshKey }) {
    const [month, setMonth] = useState(today().slice(0, 7));
    const [price, setPrice] = useState('');
    const [excluded, setExcluded] = useState([]);
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!month) return undefined;
        let cancelled = false;
        setLoading(true);
        const params = { farm: farmId, month };
        if (price) params.price = price;
        if (excluded.length) params.exclude = excluded.join(',');
        // Narx yozilayotganda har bir harfda so'rov yubormaslik uchun biroz kutamiz
        const timer = setTimeout(() => {
            api.get('animals-milk/profit/', { params })
                .then(({ data: res }) => {
                    if (cancelled) return;
                    setData(res);
                    setError('');
                })
                .catch((err) => !cancelled && setError(getErrorMessage(err, "Hisobotni yuklab bo'lmadi")))
                .finally(() => !cancelled && setLoading(false));
        }, 350);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [farmId, month, price, excluded, refreshKey]);

    const toggleCategory = (key) =>
        setExcluded((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

    const t = data?.totals;
    const losers = data ? data.cows.filter((c) => c.verdict === 'zarar' || c.verdict === 'sut_yoq').slice(0, 3) : [];

    return (
        <section className="milk-report">
            <div className="overview-head">
                <h3 className="section-title">Sut tannarxi va sigirlar foydasi</h3>
                <input type="month" value={month} max={today().slice(0, 7)}
                    onChange={(e) => setMonth(e.target.value)} aria-label="Oy" />
            </div>

            {error ? (
                <p className="error-text" role="alert">{error}</p>
            ) : loading && !data ? (
                <p className="empty-state">Yuklanmoqda...</p>
            ) : data && (
                <>
                    {data.warnings.map((w) => (
                        <p key={w} className="workers-hint" role="status">⚠️ {w}</p>
                    ))}

                    <div className="stat-grid">
                        <div className="stat-card">
                            <span className="stat-value">{t.cost_per_liter ? `${money(t.cost_per_liter)}` : '—'}</span>
                            <span className="stat-label">1 litr sut tannarxi</span>
                            <span className="stat-sub">{formatPeriod(`${data.month}-01`, 'month')}: {num(t.liters)} l, xarajat {money(t.cost)}</span>
                        </div>
                        <div className="stat-card">
                            <span className="stat-value">{t.price_per_liter ? money(t.price_per_liter) : '—'}</span>
                            <span className="stat-label">1 litr sotuv narxi</span>
                            <span className="stat-sub">
                                {t.price_source === 'sotuv' && "shu oydagi sotuvlardan"}
                                {t.price_source === 'sotuv_90' && "oxirgi 90 kundagi sotuvlardan"}
                                {t.price_source === 'qolda' && "siz kiritgan narx"}
                                {!t.price_source && "sotuv yo'q"}
                            </span>
                        </div>
                        <div className="stat-card">
                            <span className={`stat-value ${profitClass(t.profit)}`}>{money(t.profit)}</span>
                            <span className="stat-label">Sutdan foyda / zarar</span>
                        </div>
                        <div className="stat-card">
                            <span className={`stat-value ${t.losing_cows > 0 ? 'amount-out' : ''}`}>{t.losing_cows} / {t.cows}</span>
                            <span className="stat-label">Zarar keltirayotgan sigirlar</span>
                        </div>
                    </div>

                    <div className="form-row">
                        <div className="form-field">
                            <label>1 litr narxini o'zim kiritaman (so'm)</label>
                            <input type="number" min="1" step="1" inputMode="numeric" value={price}
                                placeholder="Bo'sh qolsa, sotuvlardan olinadi"
                                onChange={(e) => setPrice(e.target.value)} />
                        </div>
                    </div>

                    {data.costs.length > 0 && (
                        <div className="form-field">
                            <label>Qaysi xarajatlar hisobga olinsin</label>
                            <div className="profit-cats">
                                {data.costs.map((c) => (
                                    <label key={c.category} className="profit-cat">
                                        <input type="checkbox" checked={!excluded.includes(c.category)}
                                            onChange={() => toggleCategory(c.category)} />
                                        {c.label}: {money(c.amount)}
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    {losers.length > 0 && (
                        <div className="withdrawal-box">
                            <strong>Sotish uchun nomzodlar</strong>
                            <ul>
                                {losers.map((c) => (
                                    <li key={c.id}>
                                        №{c.tag_number}{c.name ? ` ${c.name}` : ''} —{' '}
                                        {c.verdict === 'sut_yoq'
                                            ? "bu oy sut bermagan"
                                            : `kuniga ${num(c.daily_avg)} l, zarar ${money(Math.abs(Number(c.profit)))}`}
                                        {c.break_even_daily && ` (zararsiz bo'lishi uchun kuniga ~${num(c.break_even_daily)} l kerak)`}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {data.cows.length === 0 ? (
                        <p className="empty-state">Hisoblash uchun sigir kartochkalari yo'q</p>
                    ) : (
                        <div className="report-wrap">
                            <table className="report-table">
                                <thead>
                                    <tr>
                                        <th>Sigir</th>
                                        <th>Sut, l</th>
                                        <th>Kuniga, l</th>
                                        <th>Xarajat</th>
                                        <th>Daromad</th>
                                        <th>Foyda</th>
                                        <th>Holat</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.cows.map((c) => {
                                        const v = VERDICTS[c.verdict];
                                        return (
                                            <tr key={c.id}>
                                                <td>
                                                    <Link to={`/farms/${farmId}/animals/${c.id}`} className="animal-link">
                                                        №{c.tag_number}{c.name ? ` · ${c.name}` : ''}
                                                    </Link>
                                                    {!c.active && <span className="work-badge">{c.status}</span>}
                                                </td>
                                                <td>{num(c.liters)}</td>
                                                <td>{num(c.daily_avg)}</td>
                                                <td>{money(c.cost)}</td>
                                                <td>{money(c.revenue)}</td>
                                                <td className={profitClass(c.profit)}><strong>{money(c.profit)}</strong></td>
                                                <td><span className={`work-badge ${v.cls}`}>{v.label}</span></td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}

                    <p className="workers-hint">
                        Qanday hisoblanadi: tannarx = shu oydagi chiqimlar ÷ sog'ilgan sut. Har bir sigirga qancha yem
                        ketgani alohida yozilmagani uchun umumiy xarajat sigirlar o'rtasida kunlari bo'yicha teng
                        bo'linadi; sigirning daromadi = sog'gan suti × 1 litr narxi. Nasiyaga olingan va hali
                        to'lanmagan xarajatlar kirmaydi. Qaror qabul qilishdan oldin bir necha oyni solishtiring.
                    </p>
                </>
            )}
        </section>
    );
}

export default MilkProfit;
