import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatPeriod, today } from '../utils/format';

const num = (n) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const signed = (n) => `${Number(n) > 0 ? '+' : ''}${num(n)}`;
const changeClass = (n) => (Number(n) > 0 ? 'amount-in' : Number(n) < 0 ? 'amount-out' : '');

// Sut hisoboti: tanlangan oyda har bir sigir va hamma sigirlar jami necha litr sut bergani, o'tgan oy bilan.
// farmId: ferma raqami. refreshKey o'zgarsa qayta yuklanadi.
function MilkReport({ farmId, refreshKey }) {
    const [month, setMonth] = useState(today().slice(0, 7));
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!month) return undefined;
        let cancelled = false;
        setLoading(true);
        api.get('animals-milk/summary/', { params: { farm: farmId, month } })
            .then(({ data: res }) => {
                if (cancelled) return;
                setData(res);
                setError('');
            })
            .catch((err) => !cancelled && setError(getErrorMessage(err, "Sut hisobotini yuklab bo'lmadi")))
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, month, refreshKey]);

    const monthName = (m) => formatPeriod(`${m}-01`, 'month');

    return (
        <section className="milk-report">
            <div className="overview-head">
                <h3 className="section-title">Sut hisoboti</h3>
                <input type="month" value={month} max={today().slice(0, 7)}
                    onChange={(e) => setMonth(e.target.value)} aria-label="Oy" />
            </div>

            {error ? (
                <p className="error-text" role="alert">{error}</p>
            ) : loading && !data ? (
                <p className="empty-state">Yuklanmoqda...</p>
            ) : data && (
                <>
                    <div className="stat-grid stat-grid--3">
                        <div className="stat-card">
                            <span className="stat-value">{num(data.total)} l</span>
                            <span className="stat-label">{monthName(data.month)}: hamma sigirlar jami</span>
                            <span className="stat-sub">{data.animals_count} ta sigir sut bergan</span>
                        </div>
                        <div className="stat-card">
                            <span className="stat-value">{num(data.previous_total)} l</span>
                            <span className="stat-label">O'tgan oy ({monthName(data.previous_month)})</span>
                        </div>
                        <div className="stat-card">
                            <span className={`stat-value ${changeClass(data.change)}`}>{signed(data.change)} l</span>
                            <span className="stat-label">O'tgan oyga nisbatan</span>
                        </div>
                    </div>

                    {data.animals.length === 0 ? (
                        <p className="empty-state">Bu oy va o'tgan oy uchun sut yozilmagan</p>
                    ) : (
                        <div className="report-wrap">
                            <table className="report-table">
                                <thead>
                                    <tr>
                                        <th>Sigir</th>
                                        <th>{monthName(data.month)}, l</th>
                                        <th>O'tgan oy, l</th>
                                        <th>Farq, l</th>
                                        <th>Kuniga o'rtacha, l</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.animals.map((a) => (
                                        <tr key={a.animal}>
                                            <td>
                                                <Link to={`/farms/${farmId}/animals/${a.animal}`} className="animal-link">
                                                    №{a.tag_number}{a.name ? ` · ${a.name}` : ''}
                                                </Link>
                                            </td>
                                            <td><strong>{num(a.liters)}</strong></td>
                                            <td>{num(a.previous_liters)}</td>
                                            <td className={changeClass(a.change)}>{signed(a.change)}</td>
                                            <td>{a.daily_average ? num(a.daily_average) : '—'}</td>
                                        </tr>
                                    ))}
                                    <tr>
                                        <td><strong>Jami</strong></td>
                                        <td><strong>{num(data.total)}</strong></td>
                                        <td><strong>{num(data.previous_total)}</strong></td>
                                        <td className={changeClass(data.change)}><strong>{signed(data.change)}</strong></td>
                                        <td />
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </section>
    );
}

export default MilkReport;
