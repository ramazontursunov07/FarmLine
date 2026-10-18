import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';
import { getErrorMessage } from '../utils/errors';
import { formatMoney } from '../utils/format';
import FinanceCharts from './FinanceCharts';
import { Icon } from './dashboardKit';
import { greeting, longDate, monthName, daysSince } from '../utils/dashboardDates';

const num = (n) => Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
const SHOWN = 5; // dastlab ko'rsatiladigan "e'tibor kerak" qatorlari soni

const KIND = {
    late: { icon: 'clock', label: "Muddati o'tgan" },
    stock: { icon: 'stock', label: 'Zaxira kam' },
    care: { icon: 'care', label: 'Davolanmoqda' },
    birth: { icon: 'care', label: "Tug'ishi yaqin" },
};

function formatDateTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function lateText(dueDate) {
    const d = daysSince(dueDate);
    return d === 0 ? 'bugun muddati' : `${d} kun kechikdi`;
}

function AttentionList({ rows, total }) {
    const [all, setAll] = useState(false);
    if (total === 0) {
        return (
            <div className="db-allgood">
                <Icon name="check" size={22} />
                <div>
                    <p className="db-allgood-title">Hammasi joyida</p>
                    <p className="db-allgood-text">Muddati o'tgan vazifa, kam qolgan zaxira va davolanayotgan hayvon yo'q.</p>
                </div>
            </div>
        );
    }
    const visible = all ? rows : rows.slice(0, SHOWN);
    const hidden = total - visible.length;
    return (
        <>
            <h2 className="db-attn-title">
                {total} ta ish e'tiboringizni kutmoqda
            </h2>
            <ul className="db-attn-list">
                {visible.map((r) => (
                    <li key={r.key}>
                        <Link to={r.to} className={`db-attn db-attn--${r.kind}`}>
                            <span className="db-attn-icon"><Icon name={KIND[r.kind].icon} size={18} /></span>
                            <span className="db-attn-body">
                                <span className="db-attn-name">{r.title}</span>
                                <span className="db-attn-meta">
                                    <span className="db-attn-kind">{KIND[r.kind].label}</span>
                                    {r.meta.map((m) => <span key={m}>{m}</span>)}
                                </span>
                            </span>
                            <Icon name="chevron" size={16} className="db-attn-go" />
                        </Link>
                    </li>
                ))}
            </ul>
            {(hidden > 0 || all) && rows.length > SHOWN && (
                <button type="button" className="db-more" onClick={() => setAll((v) => !v)}>
                    {all ? 'Kamroq ko\'rsatish' : `Yana ${rows.length - SHOWN} tasini ko'rsatish`}
                </button>
            )}
            {!all && total > rows.length && (
                <p className="db-attn-rest">Yana {total - rows.length} ta bor: tegishli bo'limga kirib ko'ring.</p>
            )}
        </>
    );
}

function MoneyPanel({ finance }) {
    const income = Number(finance.month.income);
    const expense = Number(finance.month.expense);
    const profit = Number(finance.month.profit);
    const prev = Number(finance.previous.profit);
    const max = Math.max(income, expense) || 1;
    const loss = profit < 0;
    const empty = income === 0 && expense === 0;
    return (
        <aside className="db-money" aria-label="Shu oy hisobi">
            <p className="db-money-month">{monthName()} oyi</p>
            {empty ? (
                <p className="db-money-empty">Bu oy hali kirim-chiqim yozilmagan.</p>
            ) : (
                <>
                    <p className="db-money-result">
                        <span className={`db-money-num${loss ? ' is-loss' : ''}`}>
                            {loss ? '−' : profit > 0 ? '+' : ''}{formatMoney(Math.abs(profit))}
                        </span>
                        <span className="db-money-word">{loss ? 'zarar' : 'foyda'}</span>
                    </p>
                    <div className="db-bars">
                        <div className="db-bar-row">
                            <span className="db-bar-label">Kirim</span>
                            <span className="db-bar-track"><span className="db-bar db-bar--in" style={{ '--w': `${(income / max) * 100}%` }} /></span>
                            <span className="db-bar-value">{formatMoney(income)}</span>
                        </div>
                        <div className="db-bar-row">
                            <span className="db-bar-label">Chiqim</span>
                            <span className="db-bar-track"><span className="db-bar db-bar--out" style={{ '--w': `${(expense / max) * 100}%` }} /></span>
                            <span className="db-bar-value">{formatMoney(expense)}</span>
                        </div>
                    </div>
                </>
            )}
            <p className="db-money-prev">
                O'tgan oy: {prev < 0 ? 'zarar ' : prev > 0 ? 'foyda ' : ''}
                <strong>{formatMoney(Math.abs(prev))}</strong>
            </p>
        </aside>
    );
}

// refreshKey o'zgarganda (ferma qo'shilsa/o'chirilsa, AI amal bajarsa) ma'lumot qayta yuklanadi.
// children: "Fermalarim" bo'limi (Dashboard beradi); u har doim ko'rinadi.
function FarmerOverview({ refreshKey, children }) {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const [farmId, setFarmId] = useState('');
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        api.get('farms/summary/', { params: farmId ? { farm: farmId } : {} })
            .then(({ data: res }) => {
                if (cancelled) return;
                setData(res);
                setError('');
            })
            .catch((err) => !cancelled && setError(getErrorMessage(err, "Umumiy ko'rinishni yuklab bo'lmadi")));
        return () => {
            cancelled = true;
        };
    }, [farmId, refreshKey]);

    const name = user.first_name || user.username;
    const hasFarms = data && data.farms.length > 0;

    let rows = [];
    let total = 0;
    if (hasFarms) {
        const { tasks, inventory, treatments } = data;
        const pregnancies = data.pregnancies || { count: 0, items: [] };
        const farmName = (id) => data.farms.find((f) => f.id === id)?.name ?? '';
        rows = [
            ...tasks.overdue_items.map((t) => ({
                key: `t${t.id}`, kind: 'late', to: `/farms/${t.farm}/tasks`, title: t.title,
                meta: [t.farm_name, t.assigned_to_name, lateText(t.due_date)].filter(Boolean),
            })),
            ...inventory.items.map((i) => ({
                key: `i${i.id}`, kind: 'stock', to: `/farms/${i.farm}/inventory`,
                title: `${i.item_name}: ${num(i.quantity)} ${i.unit} qoldi`,
                meta: [i.farm_name, `kamida ${num(i.low_stock_threshold)} ${i.unit} kerak`],
            })),
            ...treatments.items.map((e) => ({
                key: `e${e.id}`, kind: 'care', to: `/farms/${e.farm}/work`, title: e.title,
                meta: [farmName(e.farm), e.animal_group_label, `${e.days_since_start} kundan beri`].filter(Boolean),
            })),
            ...pregnancies.items.map((a) => ({
                key: `p${a.id}`, kind: 'birth', to: `/farms/${a.farm}/animals/${a.id}`,
                title: `№${a.tag_number}${a.name ? ` · ${a.name}` : ''}`,
                meta: [a.farm_name, a.days_left < 0 ? `${-a.days_left} kun kechikdi` : a.days_left === 0 ? "bugun tug'ishi kutilmoqda" : `${a.days_left} kundan keyin tug'adi`],
            })),
        ];
        total = tasks.overdue + inventory.low_count + treatments.count + pregnancies.count;
    }

    return (
        <>
            <section className="db-hero">
                <div className="db-hero-inner">
                    <div className="db-hero-main">
                        <p className="db-date">{longDate()}</p>
                        <h2 className="db-hello">{greeting()}, {name}</h2>

                        {hasFarms && data.farms.length > 1 && (
                            <div className="db-pills" role="group" aria-label="Ferma tanlash">
                                <button type="button" className="db-pill" aria-pressed={farmId === ''} onClick={() => setFarmId('')}>
                                    Hamma fermalar
                                </button>
                                {data.farms.map((f) => (
                                    <button key={f.id} type="button" className="db-pill"
                                        aria-pressed={String(f.id) === String(farmId)} onClick={() => setFarmId(f.id)}>
                                        {f.name}
                                    </button>
                                ))}
                            </div>
                        )}

                        {error && <p className="db-hero-note">{error}</p>}
                        {!error && !data && <p className="db-hero-note">Yuklanmoqda...</p>}
                        {data && !hasFarms && (
                            <p className="db-hero-note">Boshlash uchun pastdan birinchi fermangizni qo'shing.</p>
                        )}
                        {hasFarms && <AttentionList key={farmId} rows={rows} total={total} />}
                    </div>
                    {hasFarms && <MoneyPanel finance={data.finance} />}
                </div>
            </section>

            <div className="db-main">
                {children}

                {hasFarms && (
                    <>
                        <section className="db-section">
                            <h2 className="db-h2">Moliya: oxirgi 6 oy</h2>
                            <FinanceCharts farmId={farmId} refreshKey={refreshKey} />
                        </section>

                        <section className="db-section">
                            <h2 className="db-h2">Ishchilar nima qildi</h2>
                            {data.activity.length === 0 ? (
                                <p className="db-muted">Hozircha ishchilar yozuvi yo'q.</p>
                            ) : (
                                <ul className="db-activity">
                                    {data.activity.map((a, idx) => (
                                        <li key={idx}>
                                            <span className="db-activity-time">{formatDateTime(a.at)}</span>
                                            <span><strong>{a.who}</strong> {a.text}</span>
                                            <span className="db-muted">{data.farms.find((f) => f.id === a.farm)?.name ?? ''}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>
                    </>
                )}
            </div>
        </>
    );
}

export default FarmerOverview;
