import { useState, useEffect } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const num = (v) => Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 1 });

const HINTS = {
    kam: "Haqiqiy sarf ehtiyojdan ancha kam — hayvonlar yetarli yemayotgan bo'lishi mumkin yoki sarf yozilmagan.",
    kop: "Haqiqiy sarf ehtiyojdan ancha ko'p — isrof yoki ortiqcha berilayotgan bo'lishi mumkin.",
};

// Hayvon guruhlari (vazn, sut) bo'yicha kunlik yem ehtiyoji va ombordagi zaxira bilan solishtirish.
function FeedNeed({ farmId, refreshKey }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        api.get('inventory-item/feed-need/', { params: { farm: farmId } })
            .then((res) => {
                if (cancelled) return;
                setData(res.data);
                setError('');
            })
            .catch((err) => !cancelled && setError(getErrorMessage(err, "Yem ehtiyojini yuklab bo'lmadi")))
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, refreshKey]);

    if (loading && !data) return <p className="work-meta">Yuklanmoqda…</p>;
    if (error) return <p className="form-error">{error}</p>;
    if (!data) return null;

    return (
        <div className="work-card">
            <ul className="work-list">
                {data.kinds.map((k) => {
                    const need = Number(k.need_kg_per_day);
                    if (need <= 0 && !k.has_items) return null;
                    const days = k.days_left === null ? null : Number(k.days_left);
                    const low = days !== null && days < 7;
                    return (
                        <li key={k.kind} className={`work-item${low ? ' work-item--overdue' : ''}`}>
                            <div className="work-main">
                                <span className="work-title">
                                    {k.label}
                                    {low && <span className="work-badge work-badge--shoshilinch">Kam qoldi</span>}
                                </span>
                                <span className="work-meta">
                                    Kuniga kerak: <b>{num(need)} kg</b> · Omborda: <b>{num(k.stock_kg)} kg</b>
                                    {days !== null && <> · Yetadi: <b>{num(days)} kun</b></>}
                                    {!k.has_items && need > 0 && " · Omborda bu tur yem yo'q"}
                                </span>
                                {k.actual_kg_per_day !== null && (
                                    <span className="work-meta">
                                        Haqiqiy sarf (oxirgi 14 kun): {num(k.actual_kg_per_day)} kg/kun
                                    </span>
                                )}
                                {HINTS[k.compare] && <span className="work-meta">{HINTS[k.compare]}</span>}
                            </div>
                        </li>
                    );
                })}
            </ul>

            {data.categories.length > 0 && (
                <p className="work-meta">
                    Hisob: {data.categories.map((c) => `${c.label} — ${c.count} bosh`).join(', ')}
                </p>
            )}
            {data.warnings.map((w) => (
                <p key={w} className="work-meta">⚠️ {w}</p>
            ))}
            <p className="work-meta">{data.disclaimer}</p>
        </div>
    );
}

export default FeedNeed;
