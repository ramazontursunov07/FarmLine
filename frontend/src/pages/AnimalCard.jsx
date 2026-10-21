import { useState, useEffect, useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';
import InstallButton from '../components/InstallButton';

const SEXES = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const EVENT_STATUSES = { boshlangan: 'Boshlangan', davom_etmoqda: 'Davom etmoqda', yakunlangan: 'Yakunlangan' };
const COUNT_EVENTS = ['tugilish', 'olim'];
const SESSIONS = { kun: 'Butun kun', ertalab: 'Ertalab', kechqurun: 'Kechqurun' };
const EMPTY_CALF = { tag_number: '', name: '', sex: 'urgochi' };
const MAX_CALF_CARDS = 10;

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

// Tug'ishgacha: "12 kun qoldi", "bugun", "3 kun kechikdi"
function calvingLeft(days) {
    if (days == null) return '';
    if (days === 0) return 'bugun';
    return days > 0 ? `${days} kun qoldi` : `${-days} kun kechikdi`;
}

// Yoshi oylarda (sana noma'lum bo'lsa null)
function monthsOld(iso) {
    if (!iso) return null;
    const born = new Date(iso);
    const now = new Date();
    let months = (now.getFullYear() - born.getFullYear()) * 12 + now.getMonth() - born.getMonth();
    if (now.getDate() < born.getDate()) months -= 1;
    return months;
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
    const [calves, setCalves] = useState([]);
    const [withCards, setWithCards] = useState(true);
    const [pregForm, setPregForm] = useState({ pregnant_since: today(), due_date: '' });
    const [dueEdit, setDueEdit] = useState(null);
    const [pregError, setPregError] = useState('');
    const [busy, setBusy] = useState(false);

    const [milkRecords, setMilkRecords] = useState([]);
    const [editingCard, setEditingCard] = useState(false);
    const [cardForm, setCardForm] = useState(null);
    const [cardError, setCardError] = useState('');
    const [motherOptions, setMotherOptions] = useState([]);
    const [editingWeight, setEditingWeight] = useState(null);
    const [editingMilk, setEditingMilk] = useState(null);
    const [recordError, setRecordError] = useState('');
    const [editingEvent, setEditingEvent] = useState(null);
    const [eventError, setEventError] = useState('');

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            api.get(`farms/${farmId}/`),
            api.get(`animals-card/${animalId}/card/`),
            // Sut yozuvlari ro'yxati (tahrirlash/o'chirish uchun): oxirgi 30 kun. Yuklanmasa ham sahifa ishlayveradi
            api.get('animals-milk/', { params: { animal: animalId, date_from: lastDays(30)[0] } })
                .catch(() => ({ data: [] })),
        ])
            .then(([farmRes, cardRes, milkRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setData(cardRes.data);
                setMilkRecords(asList(milkRes.data));
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

    const handleCalfChange = (index, field, value) =>
        setCalves((prev) => {
            const next = Array.from({ length: Math.max(prev.length, index + 1) }, (_, i) => prev[i] || EMPTY_CALF);
            next[index] = { ...next[index], [field]: value };
            return next;
        });

    const handleCalving = async (e) => {
        e.preventDefault();
        const payload = {
            animal_group: animal.group,
            animal: Number(animalId),
            event_type: 'tugilish',
            title: `№${animal.tag_number} tug'di`,
            animal_count: Number(calvingForm.animal_count),
            start_date: calvingForm.start_date,
        };
        if (openCards) {
            payload.calves = Array.from({ length: birthCount }, (_, i) => ({ ...EMPTY_CALF, ...calves[i] })).map((c) => ({
                tag_number: c.tag_number.trim(),
                name: c.name.trim(),
                sex: c.sex,
            }));
            if (payload.calves.some((c) => !c.tag_number)) {
                setCalvingError("Har bir buzoq uchun quloq raqamini kiriting");
                return;
            }
        }
        setBusy(true);
        setCalvingError('');
        try {
            const res = await api.post('animals-event/', payload);
            const made = res?.data?.calves_created ?? [];
            setNotice(
                made.length
                    ? `Buzoq kartochkasi ochildi: ${made.map((a) => `№${a.tag_number}`).join(', ')}`
                    : (res?.data?._pending ? "Internet yo'q: yozuv saqlandi va ulanganda serverga yuboriladi." : '')
            );
            setCalvingForm({ start_date: today(), animal_count: '1' });
            setCalves([]);
            reload();
        } catch (err) {
            setCalvingError(getErrorMessage(err, "Tug'ishni saqlab bo'lmadi"));
        } finally {
            setBusy(false);
        }
    };

    const handleMarkPregnant = (e) => {
        e.preventDefault();
        const payload = { pregnant_since: pregForm.pregnant_since };
        if (pregForm.due_date) payload.due_date = pregForm.due_date;
        submit(
            async () => {
                const res = await api.patch(`animals-card/${animalId}/`, payload);
                setPregForm({ pregnant_since: today(), due_date: '' });
                return res;
            },
            setPregError,
            "Bug'ozlikni saqlab bo'lmadi"
        );
    };

    const handleSaveDue = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.patch(`animals-card/${animalId}/`, { due_date: dueEdit || null });
                setDueEdit(null);
                return res;
            },
            setPregError,
            "Tug'ish sanasini saqlab bo'lmadi"
        );
    };

    const handleClearPregnancy = async () => {
        if (!window.confirm(`№${animal.tag_number} endi bug'oz emasmi?\n\nBug'ozlik belgisi olib tashlanadi.`)) return;
        try {
            afterSave(await api.patch(`animals-card/${animalId}/`, { pregnant_since: null }));
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
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
        const wd = animal.withdrawal;
        const warning = wd
            ? `⛔ DIQQAT: bu hayvon ${wd.medicine} bilan davolangan, go'shtini ${wd.until ? `${formatDate(wd.until)} gacha` : 'davolash tugagach yana bir necha kun'} sotib bo'lmaydi!\n\n`
            : '';
        if (!window.confirm(`${warning}№${animal.tag_number} sotildi deb belgilaysizmi?`)) return;
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

    // --- Kartochkani tahrirlash (faqat ferma egasi)
    const startEditCard = async () => {
        setCardError('');
        setCardForm({
            tag_number: animal.tag_number,
            name: animal.name || '',
            sex: animal.sex,
            birth_date: animal.birth_date || '',
            mother: animal.mother ? String(animal.mother) : '',
            notes: animal.notes || '',
        });
        setEditingCard(true);
        try {
            const { data: list } = await api.get('animals-card/', { params: { farm: farmId, sex: 'urgochi' } });
            setMotherOptions(asList(list).filter((a) => String(a.id) !== String(animalId)));
        } catch {
            // ona ro'yxati yuklanmasa ham qolgan maydonlarni tahrirlash mumkin
        }
    };

    const handleCardChange = (e) => setCardForm({ ...cardForm, [e.target.name]: e.target.value });

    const handleSaveCard = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.patch(`animals-card/${animalId}/`, {
                    tag_number: cardForm.tag_number.trim(),
                    name: cardForm.name.trim(),
                    sex: cardForm.sex,
                    birth_date: cardForm.birth_date || null,
                    mother: cardForm.mother ? Number(cardForm.mother) : null,
                    notes: cardForm.notes.trim(),
                });
                setEditingCard(false);
                return res;
            },
            setCardError,
            "Kartochkani saqlab bo'lmadi"
        );
    };

    // --- Vazn yozuvini tahrirlash
    const startEditWeight = (w) => {
        setRecordError('');
        setEditingMilk(null);
        setEditingWeight({ id: w.id, date: w.date, weight_kg: w.weight_kg });
    };

    const handleSaveWeight = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.patch(`animals-weight/${editingWeight.id}/`, {
                    date: editingWeight.date, weight_kg: editingWeight.weight_kg,
                });
                setEditingWeight(null);
                return res;
            },
            setRecordError,
            "Vaznni o'zgartirib bo'lmadi"
        );
    };

    // --- Sut yozuvini tahrirlash / o'chirish (ferma egasi yoki yozuvni yozgan ishchi)
    const canModifyMilk = (r) => isOwner || (user.id != null && r.recorded_by === user.id);

    const startEditMilk = (r) => {
        setRecordError('');
        setEditingWeight(null);
        setEditingMilk({ id: r.id, date: r.date, session: r.session, liters: r.liters });
    };

    const handleSaveMilk = (e) => {
        e.preventDefault();
        submit(
            async () => {
                const res = await api.patch(`animals-milk/${editingMilk.id}/`, {
                    date: editingMilk.date, session: editingMilk.session, liters: editingMilk.liters,
                });
                setEditingMilk(null);
                return res;
            },
            setRecordError,
            "Sutni o'zgartirib bo'lmadi"
        );
    };

    const handleDeleteMilk = async (r) => {
        if (!window.confirm(`${formatDate(r.date)} (${SESSIONS[r.session] || r.session}) dagi ${r.liters} l yozuvini o'chirasizmi?`)) return;
        try {
            await api.delete(`animals-milk/${r.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    // --- Voqea (ish) yozuvini tahrirlash va o'chirish: ferma egasi yoki yozuvni yozgan ishchi
    const canEditEvent = (ev) => isOwner || ev.recorded_by === user.id;

    const startEditEvent = (ev) => {
        setEventError('');
        setEditingEvent({
            id: ev.id, title: ev.title, description: ev.description || '', start_date: ev.start_date,
            status: ev.status, isCount: COUNT_EVENTS.includes(ev.event_type),
        });
    };

    const handleSaveEvent = (e) => {
        e.preventDefault();
        const payload = {
            title: editingEvent.title.trim(), description: editingEvent.description.trim(),
            start_date: editingEvent.start_date,
        };
        if (!editingEvent.isCount) payload.status = editingEvent.status;
        submit(
            async () => {
                const res = await api.patch(`animals-event/${editingEvent.id}/`, payload);
                setEditingEvent(null);
                return res;
            },
            setEventError,
            "Yozuvni saqlab bo'lmadi"
        );
    };

    const handleDeleteEvent = async (ev) => {
        let text = `"${ev.title}" yozuvini o'chirasizmi?`;
        const newborns = ev.newborn_cards || 0;
        if (ev.event_type === 'tugilish' && ev.animal_count) {
            text += `\n\nGuruhdagi hayvonlar soni ${ev.animal_count} taga kamayadi.`;
            if (newborns > 0) text += ` ${newborns} ta buzoq kartochkasi ham o'chadi.`;
        } else if (ev.event_type === 'olim' && ev.animal_count) {
            text += `\n\nGuruhdagi hayvonlar soni ${ev.animal_count} taga ko'payadi, hayvon qaytadan faol bo'ladi.`;
        }
        if (!window.confirm(text)) return;
        try {
            await api.delete(`animals-event/${ev.id}/`, newborns > 0 ? { params: { delete_calves: 1 } } : undefined);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleDeleteCard = async () => {
        const ok = window.confirm(
            `№${animal.tag_number} kartochkasini o'chirasizmi?\n\nVazn va sut tarixi ham o'chadi. ` +
            `${isActive ? "Guruhdagi hayvonlar soni 1 taga kamayadi." : "Guruh soni o'zgarmaydi."} Buni qaytarib bo'lmaydi.`
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
    // 1 yoshgacha bo'lgan bolada (buzoq, qo'zi...) sut, bug'ozlik va tug'ish bo'limlari kerak emas
    const age = monthsOld(animal?.birth_date);
    const isYoung = age != null && age < 12;
    const showMilk = isFemale && (!isYoung || (milk?.days_recorded ?? 0) > 0);
    const canBreed = isFemale && isActive && (!isYoung || Boolean(animal?.is_pregnant));
    const birthCount = Number(calvingForm.animal_count) || 0;
    const canOpenCards = isOwner && birthCount >= 1 && birthCount <= MAX_CALF_CARDS;
    const openCards = canOpenCards && withCards;

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
                        {isOwner && !editingCard && (
                            <button type="button" className="btn-ghost btn-auto" onClick={startEditCard}>
                                Kartochkani tahrirlash
                            </button>
                        )}
                        {editingCard && cardForm && (
                            <form className="work-card animal-inline-form" onSubmit={handleSaveCard}>
                                <div className="form-row">
                                    <div className="form-field">
                                        <label>Quloq raqami</label>
                                        <input type="text" name="tag_number" value={cardForm.tag_number}
                                            onChange={handleCardChange} maxLength={30} required />
                                    </div>
                                    <div className="form-field">
                                        <label>Laqabi</label>
                                        <input type="text" name="name" value={cardForm.name}
                                            onChange={handleCardChange} maxLength={100} />
                                    </div>
                                </div>
                                <div className="form-row">
                                    <div className="form-field">
                                        <label>Jinsi</label>
                                        <select name="sex" value={cardForm.sex} onChange={handleCardChange}>
                                            {Object.entries(SEXES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                        </select>
                                    </div>
                                    <div className="form-field">
                                        <label>Tug'ilgan sana</label>
                                        <input type="date" name="birth_date" value={cardForm.birth_date}
                                            max={today()} onChange={handleCardChange} required />
                                    </div>
                                </div>
                                <div className="form-field">
                                    <label>Onasi</label>
                                    <select name="mother" value={cardForm.mother} onChange={handleCardChange}>
                                        <option value="">Noma'lum</option>
                                        {motherOptions.map((m) => (
                                            <option key={m.id} value={m.id}>№{m.tag_number}{m.name ? ` · ${m.name}` : ''}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-field">
                                    <label>Izoh</label>
                                    <textarea name="notes" rows="3" value={cardForm.notes} onChange={handleCardChange} />
                                </div>
                                {cardError && <p className="error-text" role="alert">{cardError}</p>}
                                <div className="farm-edit-actions">
                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                    <button type="button" className="btn-ghost btn-auto" disabled={busy}
                                        onClick={() => setEditingCard(false)}>Bekor qilish</button>
                                </div>
                            </form>
                        )}
                        {notice && <p className="workers-hint" role="status">{notice}</p>}

                        {animal.withdrawal && (
                            <div className="withdrawal-box" role="alert">
                                <strong>⛔ Sut va go'shtni sotmang</strong>
                                <span>
                                    {animal.withdrawal.medicine} bilan davolangan.{' '}
                                    {animal.withdrawal.until
                                        ? `${formatDate(animal.withdrawal.until)} gacha (${animal.withdrawal.days_left} kun qoldi) sotib bo'lmaydi.`
                                        : "Davolash tugamagan: tugagach ham ushlab turish muddati o'tishi kerak."}
                                </span>
                            </div>
                        )}

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
                            {showMilk && (
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
                            {canBreed && (
                                <div className="animal-stat">
                                    <span className="animal-stat-label">Bug'ozlik</span>
                                    <span className="animal-stat-value">{animal.is_pregnant ? "Bug'oz" : "Yo'q"}</span>
                                    <span className="animal-stat-sub">
                                        {animal.is_pregnant
                                            ? (animal.due_date
                                                ? `tug'ishi: ${formatDate(animal.due_date)} · ${calvingLeft(animal.days_to_calving)}`
                                                : "tug'ish sanasi kiritilmagan")
                                            : 'belgilanmagan'}
                                    </span>
                                </div>
                            )}
                            {isFemale && !isYoung && (
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
                                        editingWeight?.id === w.id ? (
                                            <li key={w.id} className="animal-mini-edit">
                                                <form onSubmit={handleSaveWeight} className="animal-inline-form">
                                                    <div className="form-row">
                                                        <div className="form-field">
                                                            <label>Sana</label>
                                                            <input type="date" value={editingWeight.date} max={today()}
                                                                onChange={(e) => setEditingWeight({ ...editingWeight, date: e.target.value })} required />
                                                        </div>
                                                        <div className="form-field">
                                                            <label>Vazn (kg)</label>
                                                            <input type="number" step="0.1" min="0.1" value={editingWeight.weight_kg}
                                                                onChange={(e) => setEditingWeight({ ...editingWeight, weight_kg: e.target.value })} required />
                                                        </div>
                                                    </div>
                                                    {recordError && <p className="error-text" role="alert">{recordError}</p>}
                                                    <div className="farm-edit-actions">
                                                        <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                                        <button type="button" className="btn-ghost btn-auto" disabled={busy}
                                                            onClick={() => setEditingWeight(null)}>Bekor qilish</button>
                                                    </div>
                                                </form>
                                            </li>
                                        ) : (
                                            <li key={w.id}>
                                                <span>{formatDate(w.date)}</span>
                                                <strong>{w.weight_kg} kg</strong>
                                                {isOwner && (
                                                    <>
                                                        <button type="button" className="farm-item-action"
                                                            onClick={() => startEditWeight(w)}>Tahrirlash</button>
                                                        <button type="button" className="farm-item-action farm-item-action--danger"
                                                            onClick={() => handleDeleteWeight(w)}>O'chirish</button>
                                                    </>
                                                )}
                                            </li>
                                        )
                                    ))}
                                </ul>
                            )}
                        </div>

                        {/* Sut */}
                        {showMilk && (
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
                                    {milkRecords.length > 0 && (
                                        <ul className="animal-mini-list">
                                            {milkRecords.slice(0, 10).map((r) => (
                                                editingMilk?.id === r.id ? (
                                                    <li key={r.id} className="animal-mini-edit">
                                                        <form onSubmit={handleSaveMilk} className="animal-inline-form">
                                                            <div className="form-row">
                                                                <div className="form-field">
                                                                    <label>Sana</label>
                                                                    <input type="date" value={editingMilk.date} max={today()}
                                                                        onChange={(e) => setEditingMilk({ ...editingMilk, date: e.target.value })} required />
                                                                </div>
                                                                <div className="form-field">
                                                                    <label>Vaqti</label>
                                                                    <select value={editingMilk.session}
                                                                        onChange={(e) => setEditingMilk({ ...editingMilk, session: e.target.value })}>
                                                                        {Object.entries(SESSIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                                    </select>
                                                                </div>
                                                            </div>
                                                            <div className="form-field">
                                                                <label>Sut (litr)</label>
                                                                <input type="number" step="0.1" min="0.1" value={editingMilk.liters}
                                                                    onChange={(e) => setEditingMilk({ ...editingMilk, liters: e.target.value })} required />
                                                            </div>
                                                            {recordError && <p className="error-text" role="alert">{recordError}</p>}
                                                            <div className="farm-edit-actions">
                                                                <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                                                <button type="button" className="btn-ghost btn-auto" disabled={busy}
                                                                    onClick={() => setEditingMilk(null)}>Bekor qilish</button>
                                                            </div>
                                                        </form>
                                                    </li>
                                                ) : (
                                                    <li key={r.id}>
                                                        <span>{formatDate(r.date)} · {r.session_display || SESSIONS[r.session]}</span>
                                                        <strong>{r.liters} l</strong>
                                                        {canModifyMilk(r) && (
                                                            <>
                                                                <button type="button" className="farm-item-action"
                                                                    onClick={() => startEditMilk(r)}>Tahrirlash</button>
                                                                <button type="button" className="farm-item-action farm-item-action--danger"
                                                                    onClick={() => handleDeleteMilk(r)}>O'chirish</button>
                                                            </>
                                                        )}
                                                    </li>
                                                )
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            </>
                        )}

                        {/* Bug'ozlik */}
                        {canBreed && (
                            <>
                                <h3 className="section-title">Bug'ozlik</h3>
                                <div className="work-card">
                                    {animal.is_pregnant ? (
                                        <>
                                            <p className="work-meta">
                                                Bug'oz ({formatDate(animal.pregnant_since)} dan).
                                                {animal.due_date
                                                    ? ` Taxminiy tug'ish: ${formatDate(animal.due_date)} (${calvingLeft(animal.days_to_calving)}).`
                                                    : " Taxminiy tug'ish sanasi kiritilmagan."}
                                            </p>
                                            {isOwner && (
                                                dueEdit !== null ? (
                                                    <form onSubmit={handleSaveDue} className="animal-inline-form">
                                                        <div className="form-field">
                                                            <label>Taxminiy tug'ish sanasi</label>
                                                            <input type="date" value={dueEdit} min={animal.pregnant_since}
                                                                onChange={(e) => setDueEdit(e.target.value)} />
                                                        </div>
                                                        {pregError && <p className="error-text" role="alert">{pregError}</p>}
                                                        <div className="farm-edit-actions">
                                                            <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                                            <button type="button" className="btn-ghost" onClick={() => setDueEdit(null)}>Bekor qilish</button>
                                                        </div>
                                                    </form>
                                                ) : (
                                                    <div className="farm-edit-actions">
                                                        <button type="button" className="btn-ghost"
                                                            onClick={() => { setPregError(''); setDueEdit(animal.due_date || ''); }}>
                                                            Tug'ish sanasini o'zgartirish
                                                        </button>
                                                        <button type="button" className="btn-ghost" onClick={handleClearPregnancy}>
                                                            Bug'oz emas
                                                        </button>
                                                    </div>
                                                )
                                            )}
                                            <p className="workers-hint">Tug'ishni yozsangiz, bug'ozlik belgisi o'zi olib tashlanadi.</p>
                                        </>
                                    ) : isOwner ? (
                                        <form onSubmit={handleMarkPregnant} className="animal-inline-form">
                                            <div className="form-row">
                                                <div className="form-field">
                                                    <label>Bug'ozlik boshlangan sana (urug'lantirilgan)</label>
                                                    <input type="date" value={pregForm.pregnant_since} max={today()}
                                                        onChange={(e) => setPregForm({ ...pregForm, pregnant_since: e.target.value })} required />
                                                </div>
                                                <div className="form-field">
                                                    <label>Taxminiy tug'ish sanasi (ixtiyoriy)</label>
                                                    <input type="date" value={pregForm.due_date} min={pregForm.pregnant_since}
                                                        onChange={(e) => setPregForm({ ...pregForm, due_date: e.target.value })} />
                                                </div>
                                            </div>
                                            <p className="workers-hint">Tug'ish sanasini bo'sh qoldirsangiz, hayvon turiga qarab o'zi hisoblanadi (sigir uchun 283 kun).</p>
                                            {pregError && <p className="error-text" role="alert">{pregError}</p>}
                                            <button type="submit" className="btn-primary btn-auto" disabled={busy}>Bug'oz deb belgilash</button>
                                        </form>
                                    ) : (
                                        <p className="work-meta">Bug'ozlik belgilanmagan.</p>
                                    )}
                                </div>
                            </>
                        )}

                        {/* Tug'ish */}
                        {canBreed && (
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
                                        <p className="workers-hint">
                                            {openCards
                                                ? "Guruhdagi hayvonlar soni shuncha ko'payadi va har bir buzoq uchun kartochka ochiladi."
                                                : "Guruhdagi hayvonlar soni shuncha ko'payadi. Buzoq kartochkasini keyin \"Kartochkalar\" sahifasidan onasini tanlab qo'shing."}
                                        </p>
                                        {isOwner && birthCount > MAX_CALF_CARDS && (
                                            <p className="workers-hint">
                                                {MAX_CALF_CARDS} tadan ko'p buzoq bo'lsa, kartochkalarni keyin
                                                "Hayvon kartochkalari" sahifasida oching.
                                            </p>
                                        )}
                                        {canOpenCards && (
                                            <div className="form-field">
                                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                                                    <input type="checkbox" checked={withCards}
                                                        style={{ width: 'auto', margin: 0 }}
                                                        onChange={(e) => setWithCards(e.target.checked)} />
                                                    Buzoq kartochkasini ham ochish
                                                </label>
                                            </div>
                                        )}
                                        {openCards && Array.from({ length: birthCount }, (_, i) => {
                                            const calf = calves[i] || EMPTY_CALF;
                                            return (
                                                <div className="work-card" key={i} style={{ marginBottom: 12 }}>
                                                    <p className="workers-hint" style={{ marginTop: 0 }}>{i + 1}-buzoq</p>
                                                    <div className="form-row">
                                                        <div className="form-field">
                                                            <label>Quloq raqami</label>
                                                            <input type="text" value={calf.tag_number} maxLength={30} required
                                                                placeholder="Masalan: 21"
                                                                onChange={(e) => handleCalfChange(i, 'tag_number', e.target.value)} />
                                                        </div>
                                                        <div className="form-field">
                                                            <label>Jinsi</label>
                                                            <select value={calf.sex}
                                                                onChange={(e) => handleCalfChange(i, 'sex', e.target.value)}>
                                                                {Object.entries(SEXES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                            </select>
                                                        </div>
                                                    </div>
                                                    <div className="form-field">
                                                        <label>Laqabi (ixtiyoriy)</label>
                                                        <input type="text" value={calf.name} maxLength={100}
                                                            onChange={(e) => handleCalfChange(i, 'name', e.target.value)} />
                                                    </div>
                                                </div>
                                            );
                                        })}
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
                                    editingEvent && editingEvent.id === ev.id ? (
                                        <li key={ev.id} className="work-item animal-edit">
                                            <form className="animal-edit-form" onSubmit={handleSaveEvent}>
                                                <div className="form-field">
                                                    <label>Sarlavha</label>
                                                    <input type="text" value={editingEvent.title} maxLength={255} required
                                                        onChange={(e) => setEditingEvent({ ...editingEvent, title: e.target.value })} />
                                                </div>
                                                <div className="form-row">
                                                    <div className="form-field">
                                                        <label>Sana</label>
                                                        <input type="date" value={editingEvent.start_date} required
                                                            onChange={(e) => setEditingEvent({ ...editingEvent, start_date: e.target.value })} />
                                                    </div>
                                                    {!editingEvent.isCount && (
                                                        <div className="form-field">
                                                            <label>Holati</label>
                                                            <select value={editingEvent.status}
                                                                onChange={(e) => setEditingEvent({ ...editingEvent, status: e.target.value })}>
                                                                {Object.entries(EVENT_STATUSES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                            </select>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="form-field">
                                                    <label>Izoh (ixtiyoriy)</label>
                                                    <input type="text" value={editingEvent.description}
                                                        onChange={(e) => setEditingEvent({ ...editingEvent, description: e.target.value })} />
                                                </div>
                                                {editingEvent.isCount && (
                                                    <p className="workers-hint">Tug'ilish va o'limning sonini o'zgartirib bo'lmaydi: uni o'chirib, qaytadan yozing.</p>
                                                )}
                                                {eventError && <p className="error-text" role="alert">{eventError}</p>}
                                                <div className="farm-edit-actions">
                                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                                    <button type="button" className="btn-ghost" disabled={busy} onClick={() => setEditingEvent(null)}>
                                                        Bekor qilish
                                                    </button>
                                                </div>
                                            </form>
                                        </li>
                                    ) : (
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
                                        {canEditEvent(ev) && (
                                            <div className="work-side animal-actions">
                                                <button type="button" className="btn-ghost" onClick={() => startEditEvent(ev)}>
                                                    Tahrirlash
                                                </button>
                                                <button type="button" className="farm-item-action farm-item-action--danger"
                                                    onClick={() => handleDeleteEvent(ev)}>
                                                    O'chirish
                                                </button>
                                            </div>
                                        )}
                                    </li>
                                    )
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
