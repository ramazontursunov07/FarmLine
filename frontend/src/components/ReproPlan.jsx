import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const fmt = (iso) => {
    const [, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}`;
};

const VERDICTS = {
    yaxshi: { label: 'Yaxshi', cls: 'work-badge--preg' },
    normal: { label: 'Normal', cls: '' },
    uzun: { label: 'Uzun', cls: 'work-badge--shoshilinch' },
};

function Cow({ farmId, row }) {
    return (
        <Link to={`/farms/${farmId}/animals/${row.id}`} className="animal-link">
            №{row.tag_number}{row.name ? ` · ${row.name}` : ''}
        </Link>
    );
}

function dryWhen(r) {
    if (r.days_to_dry < 0) return `${-r.days_to_dry} kun kechikdi`;
    if (r.days_to_dry === 0) return 'bugun';
    return `${r.days_to_dry} kundan keyin`;
}

// Quritish, qayta urug'lantirish va tug'ishlar orasidagi muddat: sut yo'qotishning asosiy sabablari.
function ReproPlan({ farmId, refreshKey }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let cancelled = false;
        api.get('animals-card/repro/', { params: { farm: farmId } })
            .then((res) => {
                if (cancelled) return;
                setData(res.data);
                setError('');
            })
            .catch((err) => !cancelled && setError(getErrorMessage(err, "Ko'payish eslatmalarini yuklab bo'lmadi")));
        return () => {
            cancelled = true;
        };
    }, [farmId, refreshKey]);

    if (error) return <p className="error-text" role="alert">{error}</p>;
    if (!data || data.summary.cows === 0) return null;

    const { summary: s, targets: t } = data;
    const longOnes = data.intervals.filter((r) => r.verdict === 'uzun').slice(0, 10);

    return (
        <section className="milk-report">
            <div className="overview-head">
                <h3 className="section-title">Quritish va qayta urug'lantirish</h3>
            </div>

            <div className="stat-grid">
                <div className="stat-card">
                    <span className={`stat-value ${s.dry_off > 0 ? 'amount-out' : ''}`}>{s.dry_off}</span>
                    <span className="stat-label">Quritish kerak</span>
                    <span className="stat-sub">tug'ishdan ~{t.dry_days_before} kun oldin</span>
                </div>
                <div className="stat-card">
                    <span className={`stat-value ${s.rebreed_late > 0 ? 'amount-out' : ''}`}>{s.rebreed}</span>
                    <span className="stat-label">Urug'lantirish kerak</span>
                    <span className="stat-sub">kechikkan: {s.rebreed_late}</span>
                </div>
                <div className="stat-card">
                    <span className="stat-value">{s.avg_interval ?? '—'}</span>
                    <span className="stat-label">Tug'ishlar orasi, kun</span>
                    <span className="stat-sub">me&apos;yor {t.good_interval} kungacha</span>
                </div>
                <div className="stat-card">
                    <span className="stat-value">{s.avg_days_open ?? '—'}</span>
                    <span className="stat-label">Bo&apos;sh yurgan kunlar</span>
                    <span className="stat-sub">tug&apos;gandan bug&apos;oz bo&apos;lguncha</span>
                </div>
            </div>

            {data.dry_off.length > 0 && (
                <>
                    <h4 className="section-title">🥛 Quritish vaqti</h4>
                    <ul className="work-list">
                        {data.dry_off.map((r) => (
                            <li key={r.id} className={`work-item${r.status === 'vaqti' ? ' work-item--overdue' : ''}`}>
                                <div className="work-main">
                                    <span className="work-title"><Cow farmId={farmId} row={r} /></span>
                                    <span className="work-meta">
                                        Quritish: {fmt(r.dry_date)} ({dryWhen(r)}) · tug&apos;ish: {fmt(r.due_date)}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ul>
                </>
            )}

            {data.rebreed.length > 0 && (
                <>
                    <h4 className="section-title">🐄 Qayta urug&apos;lantirish vaqti</h4>
                    <ul className="work-list">
                        {data.rebreed.map((r) => (
                            <li key={r.id} className={`work-item${r.status === 'kechikdi' ? ' work-item--overdue' : ''}`}>
                                <div className="work-main">
                                    <span className="work-title">
                                        <Cow farmId={farmId} row={r} />
                                        {r.status === 'kechikdi' && <span className="work-badge work-badge--shoshilinch">Kechikdi</span>}
                                    </span>
                                    <span className="work-meta">
                                        Tug&apos;gan: {fmt(r.last_calving)} ({r.days_since} kun oldin)
                                        {r.status === 'kechikdi' && ` · tug'ishlar orasi ~${r.projected_interval} kun bo'ladi`}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ul>
                </>
            )}

            {longOnes.length > 0 && (
                <>
                    <h4 className="section-title">⏱ Tug&apos;ishlar orasi uzun ({t.long_interval} kundan oshgan)</h4>
                    <ul className="work-list">
                        {longOnes.map((r) => (
                            <li key={r.id} className="work-item">
                                <div className="work-main">
                                    <span className="work-title">
                                        <Cow farmId={farmId} row={r} />
                                        <span className={`work-badge ${VERDICTS[r.verdict].cls}`}>{r.projected} kun</span>
                                    </span>
                                    <span className="work-meta">
                                        {r.pregnant ? 'Bug\'oz: keyingi tug\'ishgacha' : 'Bugun urug\'lantirilsa, keyingi tug\'ishgacha'} {r.projected} kun
                                        {r.gaps.length > 0 && ` · oldingilari: ${r.gaps.join(', ')} kun`}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ul>
                </>
            )}

            {data.dry_off.length === 0 && data.rebreed.length === 0 && (
                <p className="empty-state">Hozircha quritish yoki urug&apos;lantirish kerak bo&apos;lgan sigir yo&apos;q.</p>
            )}
            <p className="workers-hint">
                Tug&apos;ish yozuvlari va bug&apos;ozlik sanasidan hisoblanadi. {data.disclaimer} Bu eslatmalar Telegram kunlik hisobotiga ham chiqadi.
            </p>
        </section>
    );
}

export default ReproPlan;
