import { useState, useEffect } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { t } from '../i18n';

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
            .catch((err) => !cancelled && setError(getErrorMessage(err, t("Yem ehtiyojini yuklab bo'lmadi"))))
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, refreshKey]);

    if (loading && !data) return <p className="work-meta">{t('Yuklanmoqda…')}</p>;
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
                                    {low && <span className="work-badge work-badge--shoshilinch">{t('Kam qoldi')}</span>}
                                </span>
                                <span className="work-meta">
                                    {t('Kuniga kerak:')} <b>{num(need)} {t('kg')}</b> · {t('Omborda:')} <b>{num(k.stock_kg)} {t('kg')}</b>
                                    {days !== null && <> · {t('Yetadi:')} <b>{num(days)} {t('kun')}</b></>}
                                    {!k.has_items && need > 0 && ` · ${t("Omborda bu tur yem yo'q")}`}
                                </span>
                                {k.actual_kg_per_day !== null && (
                                    <span className="work-meta">
                                        {t('Haqiqiy sarf (oxirgi 14 kun):')} {num(k.actual_kg_per_day)} {t('kg/kun')}
                                    </span>
                                )}
                                {HINTS[k.compare] && <span className="work-meta">{t(HINTS[k.compare])}</span>}
                            </div>
                        </li>
                    );
                })}
            </ul>

            {data.categories.length > 0 && (
                <p className="work-meta">
                    {t('Hisob:')} {data.categories.map((c) => `${c.label} — ${c.count} ${t('bosh')}`).join(', ')}
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
