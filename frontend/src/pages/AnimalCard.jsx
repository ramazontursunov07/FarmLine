import { useState, useEffect, useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';
import InstallButton from '../components/InstallButton';

const SEXES = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const SESSIONS = { kun: 'Butun kun', ertalab: 'Ertalab', kechqurun: 'Kechqurun' };

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

// "5 oy" yoki "2 yil 3 oy"
function ageText(iso) {
    if (!iso) return '';
    const born = new Date(iso);
    const now = new Date();
    let months = (now.getFullYear() - born.getFullYear()) * 12 + now.getMonth() - born.getMonth();
    if (now.getDate() < born.getDate()) months -= 1;
    if (months < 0) return '';
    const years = Math.floor(months / 12);
    const rest = months % 12;
    if (years === 0) return `${rest} oy`;
    return rest ? `${years} yil ${rest} oy` : `${years} yil`;
}

// Oxirgi n kunning sanalari (eskidan yangiga), mahalliy vaqt bilan
function lastDays(n) {
    const out = [];
    for (let i = n - 1; i >= 0; i -= 1) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        out.push(d.toLocaleDateString('en-CA'));
    }
    return out;
}

function WeightChart({ weights }) {
    if (weights.length < 2) {
        return <p className="empty-state">Grafik uchun kamida 2 ta vazn kerak</p>;
    }
    const W = 320;
    const H = 130;
    const pad = 26;
    const values = weights.map((w) => Number(w.weight_kg));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const t0 = new Date(weights[0].date).getTime();
    const t1 = new Date(weights[weights.length - 1].date).getTime();
    const tSpan = t1 - t0 || 1;
    const points = weights.map((w) => {
        const x = pad + ((new Date(w.date).getTime() - t0) / tSpan) * (W - pad * 2);
        const y = H - pad - ((Number(w.weight_kg) - min) / span) * (H - pad * 2);
        return [x, y, w];
    });
    return (
        <svg className="animal-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Vazn grafigi">
            <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points.map(([x, y]) => `${x},${y}`).join(' ')} />
            {points.map(([x, y, w]) => (
                <circle key={w.id} cx={x} cy={y} r="3" fill="currentColor"><title>{`${formatDate(w.date)}: ${w.weight_kg} kg`}</title></circle>
            ))}
            <text x={pad} y="12" className="animal-chart-label">{max} kg</text>
            <text x={pad} y={H - 6} className="animal-chart-label">{min} kg</text>
            <text x={W - pad} y={H - 6} textAnchor="end" className="animal-chart-label">{formatDate(weights[weights.length - 1].date)}</text>
        </svg>
    );
}

function MilkChart({ daily }) {
    const days = lastDays(30);
    const byDate = Object.fromEntries(daily.map((r) => [r.date, Number(r.liters)]));
    const max = Math.max(1, ...days.map((d) => byDate[d] || 0));
    const W = 320;
    const H = 110;
    const barW = W / days.length;
    return (
        <svg className="animal-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Oxirgi 30 kunlik sut">
            {days.map((d, i) => {
                const v = byDate[d] || 0;
                const h = (v / max) * (H - 22);
                return (
                    <rect key={d} x={i * barW + 1} y={H - 16 - h} width={Math.max(1, barW - 2)} height={h} fill="currentColor">
                        <title>{`${formatDate(d)}: ${v} l`}</title>
                    </rect>
                );
            })}
            <text x="0" y={H - 3} className="animal-chart-label">{formatDate(days[0])}</text>
            <text x={W} y={H - 3} textAnchor="end" className="animal-chart-label">{formatDate(days[days.length - 1])}</text>
            <text x={W} y="10" textAnchor="end" className="animal-chart-label">max {max} l</text>
        </svg>
    );
}

function AnimalCard() {
    const { farmId, animalId } = useParams();
    const navigate = useNavigate();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);
    const [notice, setNotice] = useState('');

    const [weightForm, setWeightForm] = useState({ date: today(), weight_kg: '' });
    const [weightError, setWeightError] = useState('');
    const [milkForm, setMilkForm] = useState({ date: today(), session: 'kun', liters: '' });
    const [milkError, setMilkError] = useState('');
    const [calvingForm, setCalvingForm] = useState({ start_date: today(), animal_count: '1' });
    const [calvingError, setCalvingError] = useState('');
    const [busy, setBusy] = useState(false);

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        Promise.all([api.get(`farms/${farmId}/`), api.get(`animals-card/${animalId}/card/`)])
            .then(([farmRes, cardRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setData(cardRes.data);
                setError('');
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? 'Hayvon topilmadi' : getErrorMessage(err, "Ma'lumotlarni yuklab bo'lmadi"));
                }
            })
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, animalId, reloadKey]);

    const isOwner = farm ? farm.owner_username === user.username : false;
    const animal = data?.animal;
    const isActive = animal?.status === 'faol';
    const isFemale = animal?.sex === 'urgochi';

    const weightsDesc = useMemo(() => (data ? [...data.weights].reverse() : []), [data]);

    // Offline bo'lsa yozuv navbatga qo'yiladi (javobda _pending bo'ladi)
    const afterSave = (res) => {
        setNotice(res?.data?._pending ? "Internet yo'q: yozuv saqlandi va ulanganda serverga yuboriladi." : '');
        reload();
    };

    const submit = async (fn, setErr, fallback) => {
        setBusy(true);
        setErr('');
        try {
            afterSave(await fn());
        } catch (err) {
            setErr(getErrorMessage(err, fallback));
        } finally {
            setBusy(false);
        }
    };

    const handleWeight = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.post('animals-weight/', {
                    animal: Number(animalId), date: weightForm.date, weight_kg: weightForm.weight_kg,
                });
                setWeightForm({ date: today(), weight_kg: '' });
                return res;
            },
            setWeightError,
            "Vaznni saqlab bo'lmadi"
        );
    };

    const handleMilk = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.post('animals-milk/', {
                    animal: Number(animalId), date: milkForm.date, session: milkForm.session, liters: milkForm.liters,
                });
                setMilkForm({ ...milkForm, liters: '' });
                return res;
            },
            setMilkError,
            "Sutni saqlab bo'lmadi"
        );
    };

    const handleCalving = (e) => {
        e.preventDefault();
        submit(
            () => api.post('animals-event/', {
                animal_group: animal.group,
                animal: Number(animalId),
                event_type: 'tugilish',
                title: `№${animal.tag_number} tug'di`,
                animal_count: Number(calvingForm.animal_count),
                start_date: calvingForm.start_date,
            }),
            setCalvingError,
            "Tug'ishni saqlab bo'lmadi"
        );
    };

    const handleDeath = async () => {
        if (!window.confirm(`№${animal.tag_number} o'ldi deb yozasizmi?\n\nGuruhdagi hayvonlar soni 1 taga kamayadi.`)) return;
        try {
            afterSave(await api.post('animals-event/', {
                animal_group: animal.group,
                animal: Number(animalId),
                event_type: 'olim',
                animal_count: 1,
                title: `№${animal.tag_number} o'ldi`,
                start_date: today(),
            }));
        } catch (err) {
            window.alert(getErrorMessage(err, "O'limni yozib bo'lmadi"));
        }
    };

    const handleSold = async () => {
        if (!window.confirm(`№${animal.tag_number} sotildi deb belgilaysizmi?`)) return;
        try {
            await api.patch(`animals-card/${animalId}/`, { status: 'sotilgan' });
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleDeleteWeight = async (w) => {
        if (!window.confirm(`${formatDate(w.date)} dagi ${w.weight_kg} kg yozuvini o'chirasizmi?`)) return;
        try {
            await api.delete(`animals-weight/${w.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleDeleteCard = async () => {
        const ok = window.confirm(
            `№${animal.tag_number} kartochkasini o'chirasizmi?\n\nVazn va sut tarixi ham o'chadi. Guruh soni o'zgarmaydi. Buni qaytarib bo'lmaydi.`
        );
        if (!ok) return;
        try {
            await api.delete(`animals-card/${animalId}/`);
            navigate(`/farms/${farmId}/animals`);
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const ws = data?.weight_summary;
    const milk = data?.milk;
    const change = ws?.change_kg != null ? Number(ws.change_kg) : null;

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <Link to="/profile" className="user-link">Profil</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={logout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <Link to={`/farms/${farmId}/animals`} className="back-link">← Kartochkalarga qaytish</Link>

                {loading ? (
                    <p className="empty-state">Yuklanmoqda...</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">
                            №{animal.tag_number}{animal.name ? ` · ${animal.name}` : ''}
                            {!isActive && <span className="work-badge">{animal.status_display}</span>}
                        </h2>
                        <p className="panel-subtitle">
                            {animal.group_label} · {SEXES[animal.sex] || animal.sex}
                            {animal.birth_date ? ` · ${formatDate(animal.birth_date)} (${ageText(animal.birth_date)})` : ''}
                            {animal.mother_tag ? ` · onasi: №${animal.mother_tag}` : ''}
                        </p>
                        {animal.notes && <p className="work-desc">{animal.notes}</p>}
                        {notice && <p className="workers-hint" role="status">{notice}</p>}

                        <div className="animal-stats">
                            <div className="animal-stat">
                                <span className="animal-stat-label">Oxirgi vazn</span>
                                <span className="animal-stat-value">{ws.last ? `${ws.last} kg` : '—'}</span>
                                <span className="animal-stat-sub">
                                    {ws.last_date ? formatDate(ws.last_date) : "yozilmagan"}
                                    {change != null && ` · ${change > 0 ? '+' : ''}${change} kg`}
                                    {ws.daily_gain_g != null && ` · ${ws.daily_gain_g} g/kun`}
                                </span>
                            </div>
                            {isFemale && (
                                <div className="animal-stat">
                                    <span className="animal-stat-label">Sut (30 kun, o'rtacha)</span>
                                    <span className="animal-stat-value">{milk.daily_average ? `${milk.daily_average} l` : '—'}</span>
                                    <span className="animal-stat-sub">
                                        {milk.days_recorded > 0
                                            ? `${milk.days_recorded} kun yozilgan · jami ${milk.total_liters} l`
                                            : 'yozilmagan'}
                                    </span>
                                </div>
                            )}
                            {isFemale && (
                                <div className="animal-stat">
                                    <span className="animal-stat-label">Oxirgi tug'ish</span>
                                    <span className="animal-stat-value">{data.last_calving_date ? formatDate(data.last_calving_date) : '—'}</span>
                                    <span className="animal-stat-sub">{data.calves.length} ta buzoq kartochkasi</span>
                                </div>
                            )}
                        </div>

                        {/* Vazn */}
                        <h3 className="section-title">Vazn tarixi</h3>
                        <div className="work-card">
                            <WeightChart weights={data.weights} />
                            {isActive && (
                                <form onSubmit={handleWeight} className="animal-inline-form">
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Sana</label>
                                            <input type="date" value={weightForm.date} max={today()}
                                                onChange={(e) => setWeightForm({ ...weightForm, date: e.target.value })} required />
                                        </div>
                                        <div className="form-field">
                                            <label>Vazn (kg)</label>
                                            <input type="number" step="0.1" min="0.1" value={weightForm.weight_kg}
                                                onChange={(e) => setWeightForm({ ...weightForm, weight_kg: e.target.value })} required />
                                        </div>
                                    </div>
                                    {weightError && <p className="error-text" role="alert">{weightError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>Vaznni yozish</button>
                                </form>
                            )}
                            {weightsDesc.length > 0 && (
                                <ul className="animal-mini-list">
                                    {weightsDesc.slice(0, 10).map((w) => (
                                        <li key={w.id}>
                                            <span>{formatDate(w.date)}</span>
                                            <strong>{w.weight_kg} kg</strong>
                                            {isOwner && (
                                                <button type="button" className="farm-item-action farm-item-action--danger"
                                                    onClick={() => handleDeleteWeight(w)}>O'chirish</button>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>

                        {/* Sut */}
                        {isFemale && (
                            <>
                                <h3 className="section-title">Sut miqdori</h3>
                                <div className="work-card">
                                    <MilkChart daily={milk.daily} />
                                    {isActive && (
                                        <form onSubmit={handleMilk} className="animal-inline-form">
                                            <div className="form-row">
                                                <div className="form-field">
                                                    <label>Sana</label>
                                                    <input type="date" value={milkForm.date} max={today()}
                                                        onChange={(e) => setMilkForm({ ...milkForm, date: e.target.value })} required />
                                                </div>
                                                <div className="form-field">
                                                    <label>Vaqti</label>
                                                    <select value={milkForm.session}
                                                        onChange={(e) => setMilkForm({ ...milkForm, session: e.target.value })}>
                                                        {Object.entries(SESSIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                    </select>
                                                </div>
                                            </div>
                                            <div className="form-field">
                                                <label>Sut (litr)</label>
                                                <input type="number" step="0.1" min="0.1" value={milkForm.liters}
                                                    onChange={(e) => setMilkForm({ ...milkForm, liters: e.target.value })} required />
                                                <p className="workers-hint">
                                                    Kuniga ikki marta sog'sangiz, "Ertalab" va "Kechqurun" ni alohida yozing. Kun jami avtomatik hisoblanadi.
                                                </p>
                                            </div>
                                            {milkError && <p className="error-text" role="alert">{milkError}</p>}
                                            <button type="submit" className="btn-primary btn-auto" disabled={busy}>Sutni yozish</button>
                                        </form>
                                    )}
                                </div>
                            </>
                        )}

                        {/* Tug'ish */}
                        {isFemale && isActive && (
                            <>
                                <h3 className="section-title">Tug'ish</h3>
                                <div className="work-card">
                                    <form onSubmit={handleCalving} className="animal-inline-form">
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Tug'ish sanasi</label>
                                                <input type="date" value={calvingForm.start_date} max={today()}
                                                    onChange={(e) => setCalvingForm({ ...calvingForm, start_date: e.target.value })} required />
                                            </div>
                                            <div className="form-field">
                                                <label>Nechta bola</label>
                                                <input type="number" min="1" step="1" value={calvingForm.animal_count}
                                                    onChange={(e) => setCalvingForm({ ...calvingForm, animal_count: e.target.value })} required />
                                            </div>
                                        </div>
                                        <p className="workers-hint">Guruhdagi hayvonlar soni shuncha ko'payadi. Buzoq kartochkasini keyin "Kartochkalar" sahifasidan onasini tanlab qo'shing.</p>
                                        {calvingError && <p className="error-text" role="alert">{calvingError}</p>}
                                        <button type="submit" className="btn-primary btn-auto" disabled={busy}>Tug'ishni yozish</button>
                                    </form>
                                </div>
                            </>
                        )}

                        {data.calves.length > 0 && (
                            <>
                                <h3 className="section-title">Buzoqlari</h3>
                                <ul className="work-list">
                                    {data.calves.map((c) => (
                                        <li key={c.id} className="work-item">
                                            <div className="work-main">
                                                <Link to={`/farms/${farmId}/animals/${c.id}`} className="animal-link">
                                                    №{c.tag_number}{c.name ? ` · ${c.name}` : ''}
                                                </Link>
                                                <span className="work-meta">
                                                    {c.birth_date ? `tug'ilgan: ${formatDate(c.birth_date)}` : ''}
                                                </span>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </>
                        )}

                        {/* Voqealar */}
                        <h3 className="section-title">Ish va voqealar</h3>
                        {data.events.length === 0 ? (
                            <p className="empty-state">Bu hayvon uchun yozuv yo'q. Davolash va vaksinatsiyani "Ferma ishlari" sahifasida yozing.</p>
                        ) : (
                            <ul className="work-list">
                                {data.events.map((ev) => (
                                    <li key={ev.id} className={`work-item work-item--${ev.status}`}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                {ev.title}
                                                <span className="work-badge">{ev.event_type_display}</span>
                                            </span>
                                            <span className="work-meta">
                                                {formatDate(ev.start_date)}{ev.end_date && ev.end_date !== ev.start_date ? ` – ${formatDate(ev.end_date)}` : ''} · {ev.status_display}
                                            </span>
                                            {ev.description && <span className="work-desc">{ev.description}</span>}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}

                        {/* Ferma egasi amallari */}
                        {isOwner && (
                            <div className="animal-owner-actions">
                                {isActive && (
                                    <>
                                        <button type="button" className="btn-ghost" onClick={handleSold}>Sotildi deb belgilash</button>
                                        <button type="button" className="farm-item-action farm-item-action--danger" onClick={handleDeath}>
                                            O'lim yozish
                                        </button>
                                    </>
                                )}
                                <button type="button" className="farm-item-action farm-item-action--danger" onClick={handleDeleteCard}>
                                    Kartochkani o'chirish
                                </button>
                            </div>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default AnimalCard;
