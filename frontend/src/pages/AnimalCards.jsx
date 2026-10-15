import { useState, useEffect, useMemo } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';

const SEXES = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const STATUSES = { faol: 'Faol', sotilgan: 'Sotilgan', olgan: "O'lgan" };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const EMPTY_FORM = { group: '', tag_number: '', name: '', sex: 'urgochi', birth_date: '', mother: '' };

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function AnimalCards() {
    const { farmId } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [groups, setGroups] = useState([]);
    const [animals, setAnimals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);

    const [form, setForm] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState('');
    const [saving, setSaving] = useState(false);

    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('faol');
    const groupFilter = searchParams.get('group') || '';

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            api.get(`farms/${farmId}/`),
            api.get('animals-group/', { params: { farm: farmId } }),
            api.get('animals-card/', { params: { farm: farmId } }),
        ])
            .then(([farmRes, groupsRes, animalsRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setGroups(asList(groupsRes.data));
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
    const activeGroups = useMemo(() => groups.filter((g) => g.status === 'faol'), [groups]);

    // Har bir guruhda nechta faol kartochka borligi (guruh sonidan oshmasligi kerak)
    const cardsPerGroup = useMemo(() => {
        const map = {};
        animals.forEach((a) => {
            if (a.status === 'faol') map[a.group] = (map[a.group] || 0) + 1;
        });
        return map;
    }, [animals]);

    const selectedGroup = form.group || (activeGroups[0] ? String(activeGroups[0].id) : '');
    const mothers = useMemo(
        () => animals.filter((a) => a.sex === 'urgochi' && a.status !== 'olgan'),
        [animals]
    );

    const visible = useMemo(() => {
        const q = search.trim().toLowerCase();
        return animals.filter(
            (a) =>
                (!groupFilter || String(a.group) === groupFilter) &&
                (!statusFilter || a.status === statusFilter) &&
                (!q || a.tag_number.toLowerCase().includes(q) || (a.name || '').toLowerCase().includes(q))
        );
    }, [animals, groupFilter, statusFilter, search]);

    const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

    const handleAdd = async (e) => {
        e.preventDefault();
        setSaving(true);
        setFormError('');
        try {
            await api.post('animals-card/', {
                group: Number(selectedGroup),
                tag_number: form.tag_number.trim(),
                name: form.name.trim(),
                sex: form.sex,
                birth_date: form.birth_date || null,
                mother: form.mother ? Number(form.mother) : null,
            });
            setForm({ ...EMPTY_FORM, group: selectedGroup });
            reload();
        } catch (err) {
            setFormError(getErrorMessage(err, "Kartochkani saqlab bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

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
                <Link to={`/farms/${farmId}/work`} className="back-link">← Ferma ishlariga qaytish</Link>

                {loading ? (
                    <p className="empty-state">Yuklanmoqda...</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm.name}: hayvon kartochkalari</h2>
                        <p className="panel-subtitle">
                            Har bir hayvon uchun alohida hisob: vazn, sut, tug'ish va davolash tarixi.
                            Kartochka ochish ixtiyoriy, guruh soni avvalgidek guruhda saqlanadi.
                        </p>

                        <div className="filter-bar">
                            <input type="search" placeholder="Quloq raqami yoki laqab" value={search}
                                onChange={(e) => setSearch(e.target.value)} />
                            <select value={groupFilter}
                                onChange={(e) => setSearchParams(e.target.value ? { group: e.target.value } : {})}>
                                <option value="">Barcha guruhlar</option>
                                {groups.map((g) => (
                                    <option key={g.id} value={g.id}>
                                        {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''}
                                    </option>
                                ))}
                            </select>
                            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                                <option value="">Barcha holatlar</option>
                                {Object.entries(STATUSES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                        </div>

                        {visible.length === 0 ? (
                            <p className="empty-state">
                                {animals.length === 0 ? "Hozircha hayvon kartochkasi yo'q" : 'Bunday kartochka topilmadi'}
                            </p>
                        ) : (
                            <ul className="work-list">
                                {visible.map((a) => (
                                    <li key={a.id} className={`work-item animal-item--${a.status}`}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                <Link to={`/farms/${farmId}/animals/${a.id}`} className="animal-link">
                                                    №{a.tag_number}{a.name ? ` · ${a.name}` : ''}
                                                </Link>
                                                {a.status !== 'faol' && <span className="work-badge">{a.status_display}</span>}
                                            </span>
                                            <span className="work-meta">
                                                {a.group_label} · {SEXES[a.sex] || a.sex}
                                                {a.birth_date ? ` · tug'ilgan: ${formatDate(a.birth_date)}` : ''}
                                            </span>
                                            <span className="work-meta">
                                                {a.last_weight ? `Vazni: ${a.last_weight} kg (${formatDate(a.last_weight_date)})` : "Vazn yozilmagan"}
                                                {a.last_calving_date ? ` · oxirgi tug'ish: ${formatDate(a.last_calving_date)}` : ''}
                                            </span>
                                        </div>
                                        <div className="work-side">
                                            <Link to={`/farms/${farmId}/animals/${a.id}`} className="btn-ghost animal-open">Ochish</Link>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}

                        {isOwner && (
                            <>
                                <h3 className="section-title">Yangi kartochka</h3>
                                <div className="work-card">
                                    {activeGroups.length === 0 ? (
                                        <p className="empty-state">
                                            Avval "Ferma ishlari" sahifasidan hayvon guruhini qo'shing.
                                        </p>
                                    ) : (
                                        <form onSubmit={handleAdd}>
                                            <div className="form-row">
                                                <div className="form-field">
                                                    <label>Hayvon guruhi</label>
                                                    <select name="group" value={selectedGroup} onChange={handleChange}>
                                                        {activeGroups.map((g) => (
                                                            <option key={g.id} value={g.id}>
                                                                {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''} ·
                                                                {' '}kartochka: {cardsPerGroup[g.id] || 0}/{g.count}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>
                                                <div className="form-field">
                                                    <label>Quloq raqami</label>
                                                    <input type="text" name="tag_number" value={form.tag_number}
                                                        onChange={handleChange} placeholder="Masalan: 14" maxLength={30} required />
                                                </div>
                                            </div>
                                            <div className="form-row">
                                                <div className="form-field">
                                                    <label>Laqabi (ixtiyoriy)</label>
                                                    <input type="text" name="name" value={form.name} onChange={handleChange} />
                                                </div>
                                                <div className="form-field">
                                                    <label>Jinsi</label>
                                                    <select name="sex" value={form.sex} onChange={handleChange}>
                                                        {Object.entries(SEXES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                    </select>
                                                </div>
                                            </div>
                                            <div className="form-row">
                                                <div className="form-field">
                                                    <label>Tug'ilgan sana (ixtiyoriy)</label>
                                                    <input type="date" name="birth_date" value={form.birth_date} onChange={handleChange} />
                                                </div>
                                                <div className="form-field">
                                                    <label>Onasi (ixtiyoriy)</label>
                                                    <select name="mother" value={form.mother} onChange={handleChange}>
                                                        <option value="">—</option>
                                                        {mothers.map((m) => (
                                                            <option key={m.id} value={m.id}>№{m.tag_number}{m.name ? ` · ${m.name}` : ''}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            </div>
                                            {formError && <p className="error-text" role="alert">{formError}</p>}
                                            <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                                                {saving ? 'Kuting...' : "Kartochka qo'shish"}
                                            </button>
                                        </form>
                                    )}
                                </div>
                            </>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default AnimalCards;
