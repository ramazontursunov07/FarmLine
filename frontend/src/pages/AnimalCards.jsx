import { useState, useEffect, useMemo } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';
import MilkEntry from '../components/MilkEntry';
import MilkReport from '../components/MilkReport';
import MilkSales from '../components/MilkSales';

const SEXES = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const STATUSES = { faol: 'Faol', sotilgan: 'Sotilgan', olgan: "O'lgan" };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

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

    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState(null);
    const [editError, setEditError] = useState('');
    const [saving, setSaving] = useState(false);

    const [adding, setAdding] = useState(false);
    const [addForm, setAddForm] = useState({ group: '', tag_number: '', name: '', sex: 'urgochi', birth_date: '', mother: '' });
    const [addError, setAddError] = useState('');
    const [addSaving, setAddSaving] = useState(false);
    const [calfMode, setCalfMode] = useState(false);

    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('faol');
    const groupFilter = searchParams.get('group') || '';

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

    const reload = () => setReloadKey((k) => k + 1);
    const isOwner = farm ? farm.owner_username === user.username : false;

    const startEdit = (a) => {
        setEditingId(a.id);
        setEditError('');
        setEditForm({
            group: String(a.group),
            tag_number: a.tag_number,
            name: a.name || '',
            sex: a.sex,
            birth_date: a.birth_date || '',
            mother: a.mother ? String(a.mother) : '',
            status: a.status,
        });
    };

    const activeGroups = groups.filter((g) => g.status === 'faol');

    const openAdd = (groupId, isCalf = false) => {
        setAddError('');
        setAddForm({
            group: groupId || groupFilter || (activeGroups[0] ? String(activeGroups[0].id) : ''),
            tag_number: '', name: '', sex: 'urgochi', birth_date: '', mother: '',
        });
        setCalfMode(isCalf);
        setAdding(true);
    };

    const mothers = animals.filter((m) => m.sex === 'urgochi' && m.status !== 'olgan');

    const handleAddChange = (e) => setAddForm({ ...addForm, [e.target.name]: e.target.value });

    const handleAdd = async (e) => {
        e.preventDefault();
        setAddSaving(true);
        setAddError('');
        try {
            await api.post('animals-card/', {
                group: Number(addForm.group),
                tag_number: addForm.tag_number.trim(),
                name: addForm.name.trim(),
                sex: addForm.sex,
                birth_date: addForm.birth_date,
                mother: addForm.mother ? Number(addForm.mother) : null,
            });
            setAdding(false);
            reload();
        } catch (err) {
            setAddError(getErrorMessage(err, "Hayvonni qo'shib bo'lmadi"));
        } finally {
            setAddSaving(false);
        }
    };

    const handleEditChange = (e) => setEditForm({ ...editForm, [e.target.name]: e.target.value });

    const handleSave = async (e, a) => {
        e.preventDefault();
        setSaving(true);
        setEditError('');
        try {
            const payload = {
                group: Number(editForm.group),
                tag_number: editForm.tag_number.trim(),
                name: editForm.name.trim(),
                sex: editForm.sex,
                birth_date: editForm.birth_date || null,
                mother: editForm.mother ? Number(editForm.mother) : null,
            };
            // "O'lgan" holati faqat o'lim yozuvi orqali o'zgaradi, shuning uchun yuborilmaydi
            if (a.status !== 'olgan') payload.status = editForm.status;
            await api.patch(`animals-card/${a.id}/`, payload);
            setEditingId(null);
            reload();
        } catch (err) {
            setEditError(getErrorMessage(err, "Kartochkani saqlab bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (a) => {
        const ok = window.confirm(
            `№${a.tag_number}${a.name ? ` (${a.name})` : ''} kartochkasini o'chirasizmi?\n\n` +
            "Uning vazn va sut tarixi ham o'chadi. " +
            (a.status === 'faol' ? "Guruhdagi hayvonlar soni 1 taga kamayadi. " : "Guruh soni o'zgarmaydi. ") +
            "Buni qaytarib bo'lmaydi."
        );
        if (!ok) return;
        try {
            await api.delete(`animals-card/${a.id}/`);
            if (editingId === a.id) setEditingId(null);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    // Kartochkasi ochilmagan hayvonlar: guruhdagi soni - faol kartochkalar soni
    const uncarded = useMemo(() => groups
        .filter((g) => g.status === 'faol' && (!groupFilter || String(g.id) === groupFilter))
        .map((g) => ({
            group: g,
            rest: g.count - animals.filter((a) => a.group === g.id && a.status === 'faol').length,
        }))
        .filter((x) => x.rest > 0), [groups, animals, groupFilter]);
    const uncardedTotal = uncarded.reduce((s, x) => s + x.rest, 0);

    const visible = useMemo(() => {
        const q = search.trim().toLowerCase();
        return animals.filter(
            (a) =>
                (!groupFilter || String(a.group) === groupFilter) &&
                (!statusFilter || a.status === statusFilter) &&
                (!q || a.tag_number.toLowerCase().includes(q) || (a.name || '').toLowerCase().includes(q))
        );
    }, [animals, groupFilter, statusFilter, search]);

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

                        <MilkEntry farmId={farmId} animals={animals} onSaved={reload} />
                        <MilkSales farmId={farmId} refreshKey={reloadKey} />
                        <MilkReport farmId={farmId} refreshKey={reloadKey} />

                        {isOwner && !adding && (
                            <button type="button" className="btn-primary btn-auto" onClick={() => openAdd()}>
                                + Hayvon qo'shish
                            </button>
                        )}
                        {isOwner && adding && (
                            <div className="work-card">
                                {activeGroups.length === 0 ? (
                                    <>
                                        <p className="work-meta">
                                            Avval hayvon guruhini oching: «Ferma ishlari» sahifasida «Hayvon guruhlari» bo'limida.
                                        </p>
                                        <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>Yopish</button>
                                    </>
                                ) : (
                                    <form className="animal-inline-form" onSubmit={handleAdd}>
                                        {calfMode && <h4 className="section-title">Buzoq kartochkasi</h4>}
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Guruhi</label>
                                                <select name="group" value={addForm.group} onChange={handleAddChange}>
                                                    {activeGroups.map((g) => (
                                                        <option key={g.id} value={g.id}>
                                                            {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div className="form-field">
                                                <label>Quloq raqami</label>
                                                <input type="text" name="tag_number" value={addForm.tag_number}
                                                    onChange={handleAddChange} maxLength={30} required />
                                            </div>
                                        </div>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Laqabi (ixtiyoriy)</label>
                                                <input type="text" name="name" value={addForm.name}
                                                    onChange={handleAddChange} maxLength={100} />
                                            </div>
                                            <div className="form-field">
                                                <label>Jinsi</label>
                                                <select name="sex" value={addForm.sex} onChange={handleAddChange}>
                                                    {Object.entries(SEXES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                </select>
                                            </div>
                                        </div>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Tug'ilgan sana</label>
                                                <input type="date" name="birth_date" value={addForm.birth_date}
                                                    max={new Date().toLocaleDateString('en-CA')} onChange={handleAddChange} required />
                                            </div>
                                            <div className="form-field">
                                                <label>Onasi (ixtiyoriy)</label>
                                                <select name="mother" value={addForm.mother} onChange={handleAddChange}>
                                                    <option value="">—</option>
                                                    {mothers.map((m) => (
                                                        <option key={m.id} value={m.id}>
                                                            №{m.tag_number}{m.name ? ` · ${m.name}` : ''}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                        <p className="workers-hint">Guruhdagi hayvonlar soni 1 taga ko'payadi.</p>
                                        {addError && <p className="error-text" role="alert">{addError}</p>}
                                        <div className="farm-edit-actions">
                                            <button type="submit" className="btn-primary btn-auto" disabled={addSaving}>
                                                {addSaving ? 'Kuting...' : "Qo'shish"}
                                            </button>
                                            <button type="button" className="btn-ghost" disabled={addSaving} onClick={() => setAdding(false)}>
                                                Bekor qilish
                                            </button>
                                        </div>
                                    </form>
                                )}
                            </div>
                        )}

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

                        {(statusFilter === '' || statusFilter === 'faol') && !search.trim() && uncarded.length > 0 && (
                            <>
                                <h3 className="section-title">Kartochkasiz hayvonlar: {uncardedTotal} ta</h3>
                                <ul className="work-list">
                                    {uncarded.map(({ group: g, rest }) => (
                                        <li key={g.id} className="work-item">
                                            <div className="work-main">
                                                <span className="work-title">
                                                    {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''}
                                                </span>
                                                <span className="work-meta">
                                                    {rest} ta hayvon, kartochkasi ochilmagan (guruhda jami {g.count} ta)
                                                </span>
                                            </div>
                                            {isOwner && (
                                                <div className="work-side animal-actions">
                                                    <button type="button" className="btn-ghost" onClick={() => openAdd(String(g.id), true)}>
                                                        Kartochka ochish
                                                    </button>
                                                </div>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            </>
                        )}

                        {visible.length === 0 ? (
                            <p className="empty-state">
                                {animals.length === 0 ? "Hozircha hayvon kartochkasi yo'q" : 'Bunday kartochka topilmadi'}
                            </p>
                        ) : (
                            <ul className="work-list">
                                {visible.map((a) => (
                                    editingId === a.id ? (
                                        <li key={a.id} className="work-item animal-edit">
                                            <form className="animal-edit-form" onSubmit={(e) => handleSave(e, a)}>
                                                <div className="form-row">
                                                    <div className="form-field">
                                                        <label>Quloq raqami</label>
                                                        <input type="text" name="tag_number" value={editForm.tag_number}
                                                            onChange={handleEditChange} maxLength={30} required />
                                                    </div>
                                                    <div className="form-field">
                                                        <label>Laqabi (ixtiyoriy)</label>
                                                        <input type="text" name="name" value={editForm.name}
                                                            onChange={handleEditChange} maxLength={100} />
                                                    </div>
                                                </div>
                                                <div className="form-row">
                                                    <div className="form-field">
                                                        <label>Jinsi</label>
                                                        <select name="sex" value={editForm.sex} onChange={handleEditChange}>
                                                            {Object.entries(SEXES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                        </select>
                                                    </div>
                                                    <div className="form-field">
                                                        <label>Tug'ilgan sana</label>
                                                        <input type="date" name="birth_date" value={editForm.birth_date}
                                                            max={new Date().toLocaleDateString('en-CA')} onChange={handleEditChange} required />
                                                    </div>
                                                </div>
                                                <div className="form-row">
                                                    <div className="form-field">
                                                        <label>Guruhi</label>
                                                        <select name="group" value={editForm.group} onChange={handleEditChange}>
                                                            {groups
                                                                .filter((g) => g.status === 'faol' || String(g.id) === editForm.group)
                                                                .map((g) => (
                                                                    <option key={g.id} value={g.id}>
                                                                        {g.animal_type_name}{g.breed ? ` (${g.breed})` : ''}
                                                                    </option>
                                                                ))}
                                                        </select>
                                                    </div>
                                                    <div className="form-field">
                                                        <label>Onasi (ixtiyoriy)</label>
                                                        <select name="mother" value={editForm.mother} onChange={handleEditChange}>
                                                            <option value="">—</option>
                                                            {animals
                                                                .filter((m) => m.sex === 'urgochi' && m.status !== 'olgan' && m.id !== a.id)
                                                                .map((m) => (
                                                                    <option key={m.id} value={m.id}>
                                                                        №{m.tag_number}{m.name ? ` · ${m.name}` : ''}
                                                                    </option>
                                                                ))}
                                                        </select>
                                                    </div>
                                                </div>
                                                {a.status !== 'olgan' && (
                                                    <div className="form-field">
                                                        <label>Holati</label>
                                                        <select name="status" value={editForm.status} onChange={handleEditChange}>
                                                            <option value="faol">Faol</option>
                                                            <option value="sotilgan">Sotilgan</option>
                                                        </select>
                                                    </div>
                                                )}
                                                {editError && <p className="error-text" role="alert">{editError}</p>}
                                                <div className="farm-edit-actions">
                                                    <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                                                        {saving ? 'Kuting...' : 'Saqlash'}
                                                    </button>
                                                    <button type="button" className="btn-ghost" disabled={saving}
                                                        onClick={() => setEditingId(null)}>
                                                        Bekor qilish
                                                    </button>
                                                </div>
                                            </form>
                                        </li>
                                    ) : (
                                    <li key={a.id} className={`work-item animal-item--${a.status}`}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                <Link to={`/farms/${farmId}/animals/${a.id}`} className="animal-link">
                                                    №{a.tag_number}{a.name ? ` · ${a.name}` : ''}
                                                </Link>
                                                {a.status !== 'faol' && <span className="work-badge">{a.status_display}</span>}
                                                {a.is_pregnant && <span className="work-badge work-badge--preg">Bug'oz</span>}
                                            </span>
                                            <span className="work-meta">
                                                {a.group_label} · {SEXES[a.sex] || a.sex}
                                                {a.birth_date ? ` · tug'ilgan: ${formatDate(a.birth_date)}` : ''}
                                            </span>
                                            <span className="work-meta">
                                                {a.last_weight ? `Vazni: ${a.last_weight} kg (${formatDate(a.last_weight_date)})` : "Vazn yozilmagan"}
                                                {a.last_calving_date ? ` · oxirgi tug'ish: ${formatDate(a.last_calving_date)}` : ''}
                                                {a.is_pregnant && a.due_date ? ` · tug'ishi: ${formatDate(a.due_date)}` : ''}
                                            </span>
                                        </div>
                                        <div className="work-side animal-actions">
                                            <Link to={`/farms/${farmId}/animals/${a.id}`} className="btn-ghost animal-open">Ochish</Link>
                                            {isOwner && (
                                                <>
                                                    <button type="button" className="btn-ghost" onClick={() => startEdit(a)}>
                                                        Tahrirlash
                                                    </button>
                                                    <button type="button" className="farm-item-action farm-item-action--danger"
                                                        onClick={() => handleDelete(a)}>
                                                        O'chirish
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </li>
                                    )
                                ))}
                            </ul>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default AnimalCards;
