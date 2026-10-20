import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';
import InstallButton from '../components/InstallButton';

const EVENT_TYPES = {
    kasallik: 'Kasallik',
    davolash: 'Davolash',
    vaksinatsiya: 'Vaksinatsiya',
    tugilish: "Tug'ilish",
    olim: "O'lim",
    vazn_olchash: "Vazn o'lchash",
};

// "Yangi ish yozuvi" formasida ko'rsatilmaydigan ish turlari: ular "Barcha hayvonlar" bo'limida, hayvon kartochkasidan yoziladi.
// Eski yozuvlar tarixda va filtrda qoladi. Tug'ilishni shu formada ham yozish kerak bo'lsa, 'tugilish' ni ro'yxatdan olib tashlang.
const HIDDEN_IN_FORM = ['tugilish', 'vazn_olchash'];

// Guruhdagi hayvonlar sonini o'zgartiradigan ish turlari: nechta ekani majburiy
const COUNT_HINTS = {
    olim: "Guruhdagi hayvonlar soni shuncha kamayadi.",
    tugilish: "Guruhdagi hayvonlar soni shuncha ko'payadi.",
};

// Bu ish turlari aniq bir hayvonga tegishli: formada quloq raqami so'raladi
const ANIMAL_EVENT_TYPES = ['kasallik', 'davolash', 'olim'];
// Sarlavha bo'sh qolsa, shu so'z qo'shilib yoziladi: "№14 kasallandi"
const AUTO_TITLES = { kasallik: 'kasallandi', davolash: 'davolanyapti', olim: "o'ldi" };

const EVENT_STATUSES = {
    boshlangan: 'Boshlangan',
    davom_etmoqda: 'Davom etmoqda',
    yakunlangan: 'Yakunlangan',
};

const GROUP_STATUSES = {
    faol: 'Faol',
    sotilgan: 'Sotilgan',
    olgan: "O'lgan",
    yoqolgan: "Yo'qolgan",
};

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const SEXES = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const EMPTY_CALF = { tag_number: '', name: '', sex: 'urgochi' };
// Tug'ilishda shuncha buzoqqacha kartochkani shu yerning o'zida ochish mumkin (ko'pi bilan forma uzayib ketmasin)
const MAX_CALF_CARDS = 10;

const makeEventForm = () => ({
    animal_group: '',
    event_type: 'davolash',
    animal_count: '',
    animal_tag: '',
    mother: '',
    title: '',
    description: '',
    start_date: today(),
    status: 'davom_etmoqda',
});

const EMPTY_GROUP_FORM = { animal_type_name: '', breed: '' };
const EMPTY_FILTERS = { event_type: '', status: '', recorded_by: '' };

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function FarmWork() {
    const { farmId } = useParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [groups, setGroups] = useState([]);
    const [types, setTypes] = useState([]);
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);

    const [eventForm, setEventForm] = useState(makeEventForm);
    const [animals, setAnimals] = useState([]);
    const [calves, setCalves] = useState([]);
    const [withCards, setWithCards] = useState(true);
    const [eventNotice, setEventNotice] = useState('');
    const [eventError, setEventError] = useState('');
    const [savingEvent, setSavingEvent] = useState(false);

    const [groupForm, setGroupForm] = useState(EMPTY_GROUP_FORM);
    const [groupError, setGroupError] = useState('');
    const [savingGroup, setSavingGroup] = useState(false);

    const [filters, setFilters] = useState(EMPTY_FILTERS);

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            api.get(`farms/${farmId}/`),
            api.get('animals-group/', { params: { farm: farmId } }),
            api.get('animals-event/', { params: { farm: farmId } }),
            api.get('animals-type/'),
            api.get('animals-card/', { params: { farm: farmId } }).catch(() => ({ data: [] })),
        ])
            .then(([farmRes, groupsRes, eventsRes, typesRes, animalsRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setGroups(asList(groupsRes.data));
                setEvents(asList(eventsRes.data));
                setTypes(asList(typesRes.data));
                setAnimals(asList(animalsRes.data));
                setError('');
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? 'Ferma topilmadi' : getErrorMessage(err, "Ma'lumotlarni yuklab bo'lmadi"));
                }
            })
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, reloadKey]);

    const isOwner = farm ? farm.owner_username === user.username : false;
    const canModify = (ev) => isOwner || ev.recorded_by === user.id;

    // Yozuvni fermer yozganmi yoki ishchi
    const roleLabel = (userId) => (farm && userId === farm.owner ? 'Fermer' : 'Ishchi');

    const activeGroups = useMemo(() => groups.filter((g) => g.status === 'faol'), [groups]);
    const selectedGroup = eventForm.animal_group || (activeGroups[0] ? String(activeGroups[0].id) : '');

    // Tug'ilish: ona tanlash (hamma uchun) va buzoq kartochkalarini ochish (faqat ferma egasi uchun)
    const isBirth = eventForm.event_type === 'tugilish';
    const birthCount = Number(eventForm.animal_count) || 0;
    const canOpenCards = isOwner && isBirth && birthCount >= 1 && birthCount <= MAX_CALF_CARDS;
    const openCards = canOpenCards && withCards;
    const mothers = useMemo(
        () => animals.filter((a) => a.sex === 'urgochi' && a.status === 'faol' && String(a.group) === selectedGroup),
        [animals, selectedGroup]
    );

    // Kasallik, davolash va o'lim: qaysi hayvon ekanini quloq raqami bilan aniqlaymiz
    const needsAnimal = ANIMAL_EVENT_TYPES.includes(eventForm.event_type);
    const groupCards = useMemo(
        () => animals.filter((a) => a.status === 'faol' && String(a.group) === selectedGroup),
        [animals, selectedGroup]
    );
    const tagTyped = eventForm.animal_tag.trim();
    const pickedAnimal = needsAnimal && tagTyped
        ? groupCards.find((a) => a.tag_number.toLowerCase() === tagTyped.toLowerCase()) ?? null
        : null;
    // Guruhda kartochka bor bo'lsa, qaysi hayvon ekanini yozish majburiy
    const animalRequired = needsAnimal && groupCards.length > 0;
    const tagStartsMatch = tagTyped
        ? groupCards.some((a) => a.tag_number.toLowerCase().startsWith(tagTyped.toLowerCase()))
        : false;

    const ongoing = useMemo(() => events.filter((e) => e.status !== 'yakunlangan'), [events]);

    const workers = useMemo(() => {
        const map = new Map();
        events.forEach((e) => {
            if (e.recorded_by) map.set(e.recorded_by, e.recorded_by_name);
        });
        return [...map.entries()];
    }, [events]);

    const history = useMemo(
        () =>
            events.filter(
                (e) =>
                    (!filters.event_type || e.event_type === filters.event_type) &&
                    (!filters.status || e.status === filters.status) &&
                    (!filters.recorded_by || String(e.recorded_by) === filters.recorded_by)
            ),
        [events, filters]
    );

    const handleEventChange = (e) => {
        const { name, value } = e.target;
        // Guruh almashsa, tanlangan ona va quloq raqami ham shu guruhniki bo'lmay qoladi
        setEventForm({
            ...eventForm,
            [name]: value,
            ...(name === 'animal_group' ? { mother: '', animal_tag: '' } : {}),
        });
    };

    const handleCalfChange = (index, field, value) =>
        setCalves((prev) => {
            const next = Array.from({ length: Math.max(prev.length, index + 1) }, (_, i) => prev[i] || EMPTY_CALF);
            next[index] = { ...next[index], [field]: value };
            return next;
        });

    const handleAddEvent = async (e) => {
        e.preventDefault();
        setEventError('');
        setEventNotice('');

        const { mother, animal_tag: _tag, ...fields } = eventForm;
        const payload = {
            ...fields,
            animal_group: Number(selectedGroup),
            animal_count: eventForm.animal_count ? Number(eventForm.animal_count) : null,
        };
        if (needsAnimal) {
            if (tagTyped && !pickedAnimal) {
                setEventError(
                    `Bu guruhda №${tagTyped} raqamli faol hayvon topilmadi. ` +
                    'Avval "Hayvon kartochkalari" sahifasida shu raqamli kartochka oching.'
                );
                return;
            }
            if (!tagTyped && animalRequired) {
                setEventError("Qaysi hayvon ekanini yozing (quloq raqami)");
                return;
            }
            if (pickedAnimal) {
                payload.animal = pickedAnimal.id;
                // Aniq bitta hayvon: o'limda soni 1, qolgan ish turlarida son kerak emas
                payload.animal_count = eventForm.event_type === 'olim' ? 1 : null;
                if (!payload.title.trim()) {
                    payload.title = `№${pickedAnimal.tag_number} ${AUTO_TITLES[eventForm.event_type]}`;
                }
            }
        }
        if (isBirth && mother) payload.animal = Number(mother);
        if (openCards) {
            payload.calves = Array.from({ length: birthCount }, (_, i) => ({ ...EMPTY_CALF, ...calves[i] })).map((c) => ({
                tag_number: c.tag_number.trim(),
                name: c.name.trim(),
                sex: c.sex,
            }));
            if (payload.calves.some((c) => !c.tag_number)) {
                setEventError("Har bir buzoq uchun quloq raqamini kiriting");
                return;
            }
        }
        // Tug'ilishda sarlavha bo'sh qolsa, o'zimiz yozamiz
        if (isBirth && !payload.title.trim()) {
            const tags = (payload.calves || []).map((c) => `№${c.tag_number}`).join(', ');
            payload.title = tags ? `Buzoq tug'ildi: ${tags}` : "Buzoq tug'ildi";
        }

        setSavingEvent(true);
        try {
            const { data } = await api.post('animals-event/', payload);
            const made = data?.calves_created ?? [];
            if (made.length) {
                setEventNotice(`Buzoq kartochkasi ochildi: ${made.map((a) => `№${a.tag_number}`).join(', ')}`);
            }
            setEventForm(makeEventForm());
            setCalves([]);
            reload();
        } catch (err) {
            setEventError(getErrorMessage(err, "Yozuvni saqlab bo'lmadi"));
        } finally {
            setSavingEvent(false);
        }
    };

    const handleFinish = async (ev) => {
        try {
            await api.patch(`animals-event/${ev.id}/`, { status: 'yakunlangan' });
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleDeleteEvent = async (ev) => {
        const undo = ev.animal_count && COUNT_HINTS[ev.event_type]
            ? `\n\nGuruhdagi hayvonlar soni ham ${ev.event_type === 'olim' ? 'qaytib ko\'payadi' : 'kamayadi'} (${ev.animal_count} ta).`
            : '';
        if (!window.confirm(`"${ev.title}" yozuvini o'chirasizmi?${undo}`)) return;
        try {
            await api.delete(`animals-event/${ev.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleGroupChange = (e) => setGroupForm({ ...groupForm, [e.target.name]: e.target.value });

    const handleAddGroup = async (e) => {
        e.preventDefault();
        setSavingGroup(true);
        setGroupError('');
        try {
            const name = groupForm.animal_type_name.trim();
            let type = types.find((t) => t.name.toLowerCase() === name.toLowerCase());
            if (!type) {
                const { data } = await api.post('animals-type/', { name });
                type = data;
            }
            await api.post('animals-group/', {
                farm: Number(farmId),
                animal_type: type.id,
                breed: groupForm.breed.trim(),
                count: 0, // soni kartochkalar qo'shilgan sari o'zi oshadi
            });
            setGroupForm(EMPTY_GROUP_FORM);
            reload();
        } catch (err) {
            setGroupError(getErrorMessage(err, "Guruhni qo'shib bo'lmadi"));
        } finally {
            setSavingGroup(false);
        }
    };

    // Guruhga hayvon qo'shish (sotib olingan, boshqa joydan keltirilgan va h.k.)
    const handleAddAnimals = (group) => {
        const answer = window.prompt(`${group.animal_type_name}: nechta hayvon qo'shasiz?`, '1');
        if (answer === null) return;
        const n = Number(answer);
        if (!Number.isInteger(n) || n < 1) {
            window.alert("Iltimos, 1 dan katta butun son kiriting.");
            return;
        }
        patchGroup(group, { count: group.count + n });
    };

    const patchGroup = async (group, data) => {
        try {
            await api.patch(`animals-group/${group.id}/`, data);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleDeleteGroup = async (group) => {
        const ok = window.confirm(
            `${group.animal_type_name} guruhini o'chirasizmi?\n\nUning barcha ish yozuvlari ham o'chib ketadi. Buni qaytarib bo'lmaydi.`
        );
        if (!ok) return;
        try {
            await api.delete(`animals-group/${group.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const renderEvent = (ev, { showActions }) => (
        <li key={ev.id} className={`work-item work-item--${ev.status}`}>
            <div className="work-main">
                <span className="work-title">
                    {ev.title}
                    <span className="work-badge">
                        {ev.event_type_display}{ev.animal_count ? `: ${ev.animal_count} ta` : ''}
                    </span>
                </span>
                <span className="work-meta">
                    {ev.animal_group_label}{ev.animal_tag ? ` · №${ev.animal_tag}` : ''} · {ev.animal_group_count} ta · {formatDate(ev.start_date)}
                    {ev.status !== 'yakunlangan' && ` · ${ev.days_since_start} kun`}
                    {ev.end_date && ` – ${formatDate(ev.end_date)}`}
                </span>
                {ev.description && <span className="work-desc">{ev.description}</span>}
                <span className="work-meta">
                    {ev.status_display} · Yozgan:{' '}
                    <strong>
                        {ev.recorded_by ? `${roleLabel(ev.recorded_by)} ${ev.recorded_by_name}` : "noma'lum"}
                    </strong>
                </span>
            </div>
            {showActions && canModify(ev) && (
                <div className="work-side">
                    {ev.status !== 'yakunlangan' && (
                        <button type="button" className="btn-ghost" onClick={() => handleFinish(ev)}>
                            Yakunlash
                        </button>
                    )}
                    <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDeleteEvent(ev)}>
                        O'chirish
                    </button>
                </div>
            )}
        </li>
    );

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
                <Link to="/dashboard" className="back-link">← Fermalarga qaytish</Link>

                {loading ? (
                    <p className="empty-state">Yuklanmoqda...</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm.name}: ferma ishlari</h2>
                        <p className="panel-subtitle">
                            {farm.location}
                            {isOwner ? ' · Ishchilar yozgan ishlar ham shu yerda ko\'rinadi' : ''}
                        </p>

                        <Link to={`/farms/${farmId}/animals`} className="back-link">
                            Hayvon kartochkalari (vazn, sut, tug'ish) →
                        </Link>

                        {/* Davom etayotgan ishlar */}
                        <h3 className="section-title">Davom etayotgan ishlar</h3>
                        {ongoing.length === 0 ? (
                            <p className="empty-state">Hozir davom etayotgan ish yo'q</p>
                        ) : (
                            <ul className="work-list">{ongoing.map((ev) => renderEvent(ev, { showActions: true }))}</ul>
                        )}

                        {/* Yangi yozuv */}
                        <h3 className="section-title">Yangi ish yozuvi</h3>
                        <div className="work-card">
                            {eventNotice && <p className="success-text" role="status">{eventNotice}</p>}
                            {activeGroups.length === 0 ? (
                                <p className="empty-state">
                                    {isOwner
                                        ? "Avval pastdagi \"Hayvon guruhlari\" bo'limidan hayvon guruhini qo'shing."
                                        : "Fermer hali hayvon guruhini qo'shmagan."}
                                </p>
                            ) : (
                                <form onSubmit={handleAddEvent}>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Hayvon guruhi</label>
                                            <select name="animal_group" value={selectedGroup} onChange={handleEventChange}>
                                                {activeGroups.map((g) => (
                                                    <option key={g.id} value={g.id}>
                                                        {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''} — {g.count} ta
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="form-field">
                                            <label>Ish turi</label>
                                            <select name="event_type" value={eventForm.event_type} onChange={handleEventChange}>
                                                {Object.entries(EVENT_TYPES)
                                                    .filter(([v]) => !HIDDEN_IN_FORM.includes(v))
                                                    .map(([v, l]) => (
                                                        <option key={v} value={v}>{l}</option>
                                                    ))}
                                            </select>
                                        </div>
                                    </div>
                                    {needsAnimal && (
                                        <div className="form-field">
                                            <label>{animalRequired ? 'Qaysi hayvon? Quloq raqami' : 'Quloq raqami (ixtiyoriy)'}</label>
                                            <input type="text" name="animal_tag" list="group-animal-tags" autoComplete="off"
                                                value={eventForm.animal_tag} onChange={handleEventChange}
                                                placeholder="Masalan: 14" maxLength={30} required={animalRequired} />
                                            <datalist id="group-animal-tags">
                                                {groupCards.map((a) => (
                                                    <option key={a.id} value={a.tag_number} label={a.name || undefined} />
                                                ))}
                                            </datalist>
                                            {pickedAnimal ? (
                                                <p className="workers-hint">
                                                    №{pickedAnimal.tag_number}{pickedAnimal.name ? ` · ${pickedAnimal.name}` : ''}
                                                    {eventForm.event_type === 'olim'
                                                        ? ` · kartochka "O'lgan" bo'ladi va guruh soni 1 taga kamayadi.`
                                                        : ' · yozuv shu hayvonning kartochkasida ham ko\'rinadi.'}
                                                </p>
                                            ) : tagTyped && tagStartsMatch ? (
                                                <p className="workers-hint">Ro'yxatdan hayvonni tanlang yoki raqamni oxirigacha yozing.</p>
                                            ) : tagTyped ? (
                                                <p className="error-text" role="alert">
                                                    Bu guruhda №{tagTyped} raqamli faol hayvon topilmadi.
                                                </p>
                                            ) : groupCards.length === 0 ? (
                                                <p className="workers-hint">
                                                    Bu guruhda hayvon kartochkasi yo'q, shuning uchun yozuv butun guruhga yoziladi.
                                                    Aniq hayvon uchun avval "Hayvon kartochkalari" sahifasida kartochka oching.
                                                </p>
                                            ) : null}
                                        </div>
                                    )}
                                    {!pickedAnimal && (
                                        <div className="form-field">
                                            <label>
                                                {COUNT_HINTS[eventForm.event_type] ? 'Nechta hayvon' : 'Nechta hayvon (ixtiyoriy)'}
                                            </label>
                                            <input type="number" name="animal_count" min="1" step="1"
                                                value={eventForm.animal_count} onChange={handleEventChange}
                                                required={Boolean(COUNT_HINTS[eventForm.event_type])} />
                                            {COUNT_HINTS[eventForm.event_type] && (
                                                <p className="workers-hint">
                                                    {openCards
                                                        ? "Guruhdagi hayvonlar soni shuncha ko'payadi va har bir buzoq uchun kartochka ochiladi."
                                                        : COUNT_HINTS[eventForm.event_type]}
                                                </p>
                                            )}
                                        </div>
                                    )}
                                    {isBirth && (
                                        <div className="form-field">
                                            <label>Onasi (ixtiyoriy)</label>
                                            <select name="mother" value={eventForm.mother} onChange={handleEventChange}>
                                                <option value="">—</option>
                                                {mothers.map((m) => (
                                                    <option key={m.id} value={m.id}>
                                                        №{m.tag_number}{m.name ? ` · ${m.name}` : ''}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}
                                    {isOwner && isBirth && birthCount > MAX_CALF_CARDS && (
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
                                    <div className="form-field">
                                        <label>Sarlavha</label>
                                        <input type="text" name="title" value={eventForm.title} onChange={handleEventChange}
                                            placeholder={isBirth || pickedAnimal
                                                ? "Bo'sh qoldirsangiz, avtomatik yoziladi"
                                                : 'Masalan: 10 ta tovuq antibiotik bilan davolanyapti'}
                                            required={!isBirth && !pickedAnimal} />
                                    </div>
                                    <div className="form-field">
                                        <label>Izoh (ixtiyoriy)</label>
                                        <input type="text" name="description" value={eventForm.description} onChange={handleEventChange} />
                                    </div>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Boshlangan sana</label>
                                            <input type="date" name="start_date" value={eventForm.start_date} onChange={handleEventChange} required />
                                        </div>
                                        {!COUNT_HINTS[eventForm.event_type] && (
                                            <div className="form-field">
                                                <label>Holati</label>
                                                <select name="status" value={eventForm.status} onChange={handleEventChange}>
                                                    {Object.entries(EVENT_STATUSES).map(([v, l]) => (
                                                        <option key={v} value={v}>{l}</option>
                                                    ))}
                                                </select>
                                            </div>
                                        )}
                                    </div>
                                    {eventError && <p className="error-text" role="alert">{eventError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={savingEvent}>
                                        {savingEvent ? 'Kuting...' : "Qo'shish"}
                                    </button>
                                </form>
                            )}
                        </div>

                        {/* Hayvon guruhlari */}
                        <h3 className="section-title">Hayvon guruhlari</h3>
                        {groups.length === 0 ? (
                            <p className="empty-state">Hozircha hayvon guruhi yo'q</p>
                        ) : (
                            <ul className="work-list">
                                {groups.map((g) => (
                                    <li key={g.id} className="work-item">
                                        <div className="work-main">
                                            <span className="work-title">
                                                {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''}
                                            </span>
                                            <span className="work-meta">
                                                {g.count} ta{g.birth_date ? ` · tug'ilgan: ${formatDate(g.birth_date)}` : ''}
                                                {!isOwner && ` · ${g.status_display}`}
                                            </span>
                                        </div>
                                        <div className="work-side">
                                            <Link to={`/farms/${farmId}/animals?group=${g.id}`} className="farm-item-action">
                                                Kartochkalar
                                            </Link>
                                        </div>
                                        {isOwner && (
                                            <div className="work-side">
                                                {g.status === 'faol' && (
                                                    <button type="button" className="farm-item-action" onClick={() => handleAddAnimals(g)}>
                                                        + Hayvon qo'shish
                                                    </button>
                                                )}
                                                <select value={g.status} onChange={(e) => patchGroup(g, { status: e.target.value })}>
                                                    {Object.entries(GROUP_STATUSES).map(([v, l]) => (
                                                        <option key={v} value={v}>{l}</option>
                                                    ))}
                                                </select>
                                                <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDeleteGroup(g)}>
                                                    O'chirish
                                                </button>
                                            </div>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}

                        {isOwner && (
                            <div className="work-card">
                                <form onSubmit={handleAddGroup}>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Hayvon turi</label>
                                            <input type="text" name="animal_type_name" list="animal-types"
                                                value={groupForm.animal_type_name} onChange={handleGroupChange}
                                                placeholder="Masalan: Tovuq, Qo'y, Sigir" required />
                                            <datalist id="animal-types">
                                                {types.map((t) => <option key={t.id} value={t.name} />)}
                                            </datalist>
                                        </div>
                                        <div className="form-field">
                                            <label>Zoti (ixtiyoriy)</label>
                                            <input type="text" name="breed" value={groupForm.breed} onChange={handleGroupChange} />
                                        </div>
                                    </div>
                                    {groupError && <p className="error-text" role="alert">{groupError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={savingGroup}>
                                        {savingGroup ? 'Kuting...' : "Guruh qo'shish"}
                                    </button>
                                </form>
                            </div>
                        )}

                        {/* Barcha yozuvlar */}
                        <h3 className="section-title">Barcha yozuvlar</h3>
                        <div className="filter-bar">
                            <select value={filters.event_type} onChange={(e) => setFilters({ ...filters, event_type: e.target.value })}>
                                <option value="">Barcha turlar</option>
                                {Object.entries(EVENT_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
                                <option value="">Barcha holatlar</option>
                                {Object.entries(EVENT_STATUSES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                            <select value={filters.recorded_by} onChange={(e) => setFilters({ ...filters, recorded_by: e.target.value })}>
                                <option value="">Kim yozgan: hammasi</option>
                                {workers.map(([id, name]) => (
                                    <option key={id} value={id}>{roleLabel(id)}: {name}</option>
                                ))}
                            </select>
                        </div>
                        {history.length === 0 ? (
                            <p className="empty-state">Yozuvlar yo'q</p>
                        ) : (
                            <ul className="work-list">{history.map((ev) => renderEvent(ev, { showActions: true }))}</ul>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default FarmWork;
