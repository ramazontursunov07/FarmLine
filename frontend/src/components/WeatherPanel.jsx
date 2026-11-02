import { useEffect, useState } from 'react';
import api from '../api/axios';
import { t, tServer } from '../i18n';

const WEEKDAYS = ['Yak', 'Dush', 'Sesh', 'Chor', 'Pay', 'Jum', 'Shan'];

function dayName(iso, i) {
    if (i === 0) return t('Bugun');
    if (i === 1) return t('Ertaga');
    const d = new Date(`${iso}T12:00:00`);
    return t(WEEKDAYS[d.getDay()]);
}

// "bugun 14:05" yoki "23.10 14:05"
function updatedText(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const pad = (n) => String(n).padStart(2, '0');
    const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    return sameDay ? t('bugun {time}', { time }) : `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${time}`;
}

function deg(v) {
    return v == null ? '—' : `${Math.round(v)}°`;
}

function WeatherPanel({ farms }) {
    const [farmId, setFarmId] = useState(null);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(false);

    const activeId = farmId && farms.some((f) => f.id === farmId) ? farmId : farms[0]?.id;

    useEffect(() => {
        if (!activeId) return undefined;
        let cancelled = false;
        setLoading(true);
        setFailed(false);
        api.get('weather/', { params: { farm: activeId } })
            .then(({ data: d }) => {
                if (!cancelled) setData(d);
            })
            .catch(() => {
                if (!cancelled) setFailed(true);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [activeId]);

    if (!activeId) return null;

    let body;
    if (loading) {
        body = <p className="db-muted">{t('Ob-havo yuklanmoqda...')}</p>;
    } else if (failed || !data) {
        body = <p className="db-muted">{t('Ob-havoni hozir olib bo\'lmadi. Internetni tekshirib, keyinroq qarang.')}</p>;
    } else if (data.status === 'no_location') {
        body = (
            <p className="db-muted">
                «{data.location}{t('» manzili bo\'yicha joy topilmadi. Fermani tahrirlab, manzilni aniqroq yozing (masalan: «Qarshi, Qashqadaryo»).')}
            </p>
        );
    } else if (data.status === 'unavailable') {
        body = <p className="db-muted">{t('Ob-havo xizmati hozir javob bermayapti. Birozdan keyin qayta urinib ko\'ring.')}</p>;
    } else {
        const today = data.days[0];
        body = (
            <>
                <div className="db-wx-now">
                    <span className="db-wx-temp">{deg(data.current.temp)}</span>
                    <div className="db-wx-meta">
                        <strong>{t(data.current.text) || t('Ob-havo')}</strong>
                        <span>
                            {t('Bugun')} {deg(today?.temp_min)} … {deg(today?.temp_max)} {t('· Shamol')} {Math.round(data.current.wind_kmh ?? 0)} {t('km/soat')}
                            {data.current.humidity != null ? t(' · Namlik {humidity}%', { humidity: data.current.humidity }) : ''}
                        </span>
                    </div>
                </div>

                {data.alerts.length > 0 && (
                    <ul className="db-wx-alerts">
                        {data.alerts.map((a) => (
                            <li key={`${a.type}-${a.date}`} className={`db-wx-alert db-wx-alert--${a.level}`}>
                                <b>{dayName(a.date, data.days.findIndex((d) => d.date === a.date))}:</b> {tServer(a.text)}
                            </li>
                        ))}
                    </ul>
                )}

                <ul className="db-wx-days">
                    {data.days.map((d, i) => (
                        <li key={d.date} className="db-wx-day">
                            <span className="db-wx-dname">{dayName(d.date, i)}</span>
                            <span className="db-wx-dtext">{t(d.text)}</span>
                            <span className="db-wx-dtemp">{deg(d.temp_max)} <i>{deg(d.temp_min)}</i></span>
                            <span className="db-wx-drain">
                                {d.rain_chance != null && d.rain_chance >= 30 ? t('Yog\'in {rain_chance}%', { rain_chance: d.rain_chance }) : ' '}
                            </span>
                        </li>
                    ))}
                </ul>

                {data.stale && (
                    <p className="db-muted" role="status">
                        {t('Ob-havo xizmati hozir javob bermayapti: oxirgi olingan ma\'lumot')}
                        {data.updated_at ? ` (${updatedText(data.updated_at)})` : ''} {t('ko\'rsatilyapti.')}
                    </p>
                )}
            </>
        );
    }

    return (
        <section className="db-section db-wx">
            <div className="db-wx-head">
                <h2 className="db-h2">{t('Ob-havo')}</h2>
                {farms.length > 1 ? (
                    <select className="db-wx-select" value={activeId} onChange={(e) => setFarmId(Number(e.target.value))}
                        aria-label={t('Ferma tanlang')}>
                        {farms.map((f) => (
                            <option key={f.id} value={f.id}>{f.name}</option>
                        ))}
                    </select>
                ) : (
                    <span className="db-wx-where">{farms[0].location}</span>
                )}
            </div>
            <div className="db-wx-card">{body}</div>
        </section>
    );
}

export default WeatherPanel;
