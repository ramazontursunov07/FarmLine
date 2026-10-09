import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatMoney } from '../utils/format';

const num = (n) => Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 2 });

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function formatDateTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// refreshKey: fermalar soni o'zgarganda (qo'shilsa/o'chirilsa) ma'lumot qayta yuklanadi
function FarmerOverview({ refreshKey }) {
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

    if (error) return <p className="error-text">{error}</p>;
    if (!data || data.farms.length === 0) return null;

    const { animals, treatments, tasks, inventory, finance, activity } = data;
    const farmName = (id) => data.farms.find((f) => f.id === id)?.name ?? '';
    const profit = Number(finance.month.profit);
    const prevProfit = Number(finance.previous.profit);

    const typesLine = animals.by_type.slice(0, 3).map((t) => `${t.name} ${num(t.count)}`).join(' · ');

    return (
        <div className="panel overview">
            <div className="overview-head">
                <h2 className="panel-title">Umumiy ko'rinish</h2>
                {data.farms.length > 1 && (
                    <select value={farmId} onChange={(e) => setFarmId(e.target.value)}>
                        <option value="">Barcha fermalar</option>
                        {data.farms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                    </select>
                )}
            </div>

            <div className="stat-grid stat-grid--auto">
                <div className="stat-card">
                    <span className="stat-value">{num(animals.total)}</span>
                    <span className="stat-label">Jami hayvonlar</span>
                    {typesLine && <span className="stat-sub">{typesLine}</span>}
                </div>
                <div className={`stat-card${treatments.count > 0 ? ' stat-card--warn' : ''}`}>
                    <span className="stat-value">{treatments.count}</span>
                    <span className="stat-label">Davolanayotgan</span>
                </div>
                <div className={`stat-card${inventory.low_count > 0 ? ' stat-card--warn' : ''}`}>
                    <span className="stat-value">{inventory.low_count}</span>
                    <span className="stat-label">Zaxirasi kam mahsulot</span>
                </div>
                <div className={`stat-card${tasks.overdue > 0 ? ' stat-card--warn' : ''}`}>
                    <span className="stat-value">{tasks.overdue}</span>
                    <span className="stat-label">Muddati o'tgan vazifa</span>
                    <span className="stat-sub">Jami ochiq: {tasks.open}</span>
                </div>
                <div className="stat-card">
                    <span className={`stat-value stat-value--sm ${profit < 0 ? 'amount-out' : ''}`}>
                        {profit > 0 ? '+' : ''}{formatMoney(profit)}
                    </span>
                    <span className="stat-label">Shu oy {profit < 0 ? 'zarar' : 'foyda'}</span>
                    <span className="stat-sub">
                        Kirim {formatMoney(finance.month.income)} · Chiqim {formatMoney(finance.month.expense)}
                    </span>
                    <span className="stat-sub">O'tgan oy: {prevProfit > 0 ? '+' : ''}{formatMoney(prevProfit)}</span>
                </div>
            </div>

            <div className="overview-grid">
                <section className="overview-box">
                    <h3 className="overview-box-title">Muddati o'tgan vazifalar</h3>
                    {tasks.overdue_items.length === 0 ? (
                        <p className="overview-ok">Hammasi joyida</p>
                    ) : (
                        <ul className="overview-list">
                            {tasks.overdue_items.map((t) => (
                                <li key={t.id}>
                                    <Link to={`/farms/${t.farm}/tasks`}>{t.title}</Link>
                                    <span className="work-meta">
                                        {t.farm_name} · {t.assigned_to_name} · muddat: {formatDate(t.due_date)}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="overview-box">
                    <h3 className="overview-box-title">Zaxirasi kam qolganlar</h3>
                    {inventory.items.length === 0 ? (
                        <p className="overview-ok">Hammasi joyida</p>
                    ) : (
                        <ul className="overview-list">
                            {inventory.items.map((i) => (
                                <li key={i.id}>
                                    <Link to={`/farms/${i.farm}/inventory`}>{i.item_name}</Link>
                                    <span className="work-meta">
                                        {i.farm_name} · qoldi: <strong>{num(i.quantity)} {i.unit}</strong> (chegara {num(i.low_stock_threshold)})
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="overview-box">
                    <h3 className="overview-box-title">Davolanayotganlar</h3>
                    {treatments.items.length === 0 ? (
                        <p className="overview-ok">Hozir davolanayotgan yo'q</p>
                    ) : (
                        <ul className="overview-list">
                            {treatments.items.map((e) => (
                                <li key={e.id}>
                                    <Link to={`/farms/${e.farm}/work`}>{e.title}</Link>
                                    <span className="work-meta">
                                        {farmName(e.farm)} · {e.animal_group_label} · {e.days_since_start} kun
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                    {treatments.count > treatments.items.length && (
                        <p className="work-meta">Yana {treatments.count - treatments.items.length} ta bor</p>
                    )}
                </section>

                <section className="overview-box">
                    <h3 className="overview-box-title">Ishchilarning oxirgi ishlari</h3>
                    {activity.length === 0 ? (
                        <p className="overview-ok">Hozircha ishchilar yozuvi yo'q</p>
                    ) : (
                        <ul className="overview-list">
                            {activity.map((a, idx) => (
                                <li key={idx}>
                                    <span><strong>Ishchi {a.who}:</strong> {a.text}</span>
                                    <span className="work-meta">{farmName(a.farm)} · {formatDateTime(a.at)}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </div>
        </div>
    );
}

export default FarmerOverview;
