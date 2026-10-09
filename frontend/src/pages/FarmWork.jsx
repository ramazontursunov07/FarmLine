import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';

const EVENT_TYPES = {
    kasallik: 'Kasallik',
    davolash: 'Davolash',
    vaksinatsiya: 'Vaksinatsiya',
    tugilish: "Tug'ilish",
    olim: "O'lim",
    vazn_olchash: "Vazn o'lchash",
};

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

const makeEventForm = () => ({
    animal_group: '',
    event_type: 'davolash',
    title: '',
    description: '',
    start_date: today(),
    status: 'davom_etmoqda',
});

const EMPTY_GROUP_FORM = { animal_type_name: '', breed: '', count: '', birth_date: '' };
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
        ])
            .then(([farmRes, groupsRes, eventsRes, typesRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setGroups(asList(groupsRes.data));
                setEvents(asList(eventsRes.data));
                setTypes(asList(typesRes.data));
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

    const handleEventChange = (e) => setEventForm({ ...eventForm, [e.target.name]: e.target.value });

    const handleAddEvent = async (e) => {
        e.preventDefault();
        setSavingEvent(true);
        setEventError('');
        try {
            await api.post('animals-event/', { ...eventForm, animal_group: Number(selectedGroup) });
            setEventForm(makeEventForm());
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
        if (!window.confirm(`"${ev.title}" yozuvini o'chirasizmi?`)) return;
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
                count: Number(groupForm.count),
                birth_date: groupForm.birth_date || null,
            });
            setGroupForm(EMPTY_GROUP_FORM);
            reload();
        } catch (err) {
            setGroupError(getErrorMessage(err, "Guruhni qo'shib bo'lmadi"));
        } finally {
            setSavingGroup(false);
        }
    };

    const patchGroup = async (group, data) => {
        try {
            await api.patch(`animals-group/${group.id}/`, data);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleChangeCount = (group) => {
        const value = window.prompt(`${group.animal_type_name}: yangi sonini kiriting`, group.count);
        if (value === null) return;
        const n = Number(value);
        if (!Number.isInteger(n) || n < 0) {
            window.alert("Iltimos, 0 yoki undan katta butun son kiriting");
            return;
        }
        patchGroup(group, { count: n });
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
                    <span className="work-badge">{ev.event_type_display}</span>
                </span>
                <span className="work-meta">
                    {ev.animal_group_label} · {ev.animal_group_count} ta · {formatDate(ev.start_date)}
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
                                                {Object.entries(EVENT_TYPES).map(([v, l]) => (
                                                    <option key={v} value={v}>{l}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                    <div className="form-field">
                                        <label>Sarlavha</label>
                                        <input type="text" name="title" value={eventForm.title} onChange={handleEventChange}
                                            placeholder="Masalan: 10 ta tovuq antibiotik bilan davolanyapti" required />
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
                                        <div className="form-field">
                                            <label>Holati</label>
                                            <select name="status" value={eventForm.status} onChange={handleEventChange}>
                                                {Object.entries(EVENT_STATUSES).map(([v, l]) => (
                                                    <option key={v} value={v}>{l}</option>
                                                ))}
                                            </select>
                                        </div>
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
                                        {isOwner && (
                                            <div className="work-side">
                                                <select value={g.status} onChange={(e) => patchGroup(g, { status: e.target.value })}>
                                                    {Object.entries(GROUP_STATUSES).map(([v, l]) => (
                                                        <option key={v} value={v}>{l}</option>
                                                    ))}
                                                </select>
                                                <button type="button" className="farm-item-action" onClick={() => handleChangeCount(g)}>
                                                    Sonini o'zgartirish
                                                </button>
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
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Soni</label>
                                            <input type="number" name="count" min="0" step="1" value={groupForm.count}
                                                onChange={handleGroupChange} required />
                                        </div>
                                        <div className="form-field">
                                            <label>Tug'ilgan sana (ixtiyoriy)</label>
                                            <input type="date" name="birth_date" value={groupForm.birth_date} onChange={handleGroupChange} />
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
