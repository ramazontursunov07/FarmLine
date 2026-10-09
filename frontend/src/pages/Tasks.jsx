import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const PRIORITIES = { oddiy: 'Oddiy', muhim: 'Muhim', shoshilinch: 'Shoshilinch' };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const EMPTY_FORM = { title: '', description: '', assigned_to: '', due_date: '', priority: 'oddiy' };

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function Tasks() {
    const { farmId } = useParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [tasks, setTasks] = useState([]);
    const [workers, setWorkers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);

    const [form, setForm] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState('');
    const [saving, setSaving] = useState(false);
    const [assigneeFilter, setAssigneeFilter] = useState('');

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const farmRes = await api.get(`farms/${farmId}/`);
                const owner = farmRes.data.owner_username === user.username;
                const requests = [api.get('tasks/', { params: { farm: farmId } })];
                if (owner) requests.push(api.get('workers/', { params: { farm: farmId } }));
                const [tasksRes, workersRes] = await Promise.all(requests);
                if (cancelled) return;
                setFarm(farmRes.data);
                setTasks(asList(tasksRes.data));
                setWorkers(workersRes ? asList(workersRes.data) : []);
                setError('');
            } catch (err) {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? 'Ferma topilmadi' : getErrorMessage(err, "Vazifalarni yuklab bo'lmadi"));
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [farmId, reloadKey, user.username]);

    const isOwner = farm ? farm.owner_username === user.username : false;

    const visible = useMemo(
        () => tasks.filter((t) => !assigneeFilter || (assigneeFilter === 'all' ? !t.assigned_to : String(t.assigned_to) === assigneeFilter)),
        [tasks, assigneeFilter]
    );

    // Bajarilmaganlar: muddati o'tganlar birinchi, keyin muddati yaqinlari, muddatsizlar oxirida
    const open = useMemo(
        () =>
            visible
                .filter((t) => t.status !== 'bajarildi')
                .sort((a, b) => {
                    if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
                    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
                    if (a.due_date) return -1;
                    if (b.due_date) return 1;
                    return 0;
                }),
        [visible]
    );
    const done = useMemo(() => visible.filter((t) => t.status === 'bajarildi'), [visible]);

    const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

    const handleAdd = async (e) => {
        e.preventDefault();
        setSaving(true);
        setFormError('');
        try {
            await api.post('tasks/', {
                farm: Number(farmId),
                title: form.title,
                description: form.description,
                assigned_to: form.assigned_to ? Number(form.assigned_to) : null,
                due_date: form.due_date || null,
                priority: form.priority,
            });
            setForm(EMPTY_FORM);
            reload();
        } catch (err) {
            setFormError(getErrorMessage(err, "Vazifani saqlab bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const patch = async (task, data) => {
        try {
            await api.patch(`tasks/${task.id}/`, data);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleFinish = (task) => {
        const note = window.prompt('Bajarilgan ish haqida izoh (ixtiyoriy):', '');
        if (note === null) return; // Bekor qilindi
        patch(task, { status: 'bajarildi', result_note: note.trim() });
    };

    const handleDelete = async (task) => {
        if (!window.confirm(`"${task.title}" vazifasini o'chirasizmi?`)) return;
        try {
            await api.delete(`tasks/${task.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const renderTask = (t) => (
        <li key={t.id} className={`work-item work-item--${t.status}${t.is_overdue ? ' work-item--overdue' : ''}`}>
            <div className="work-main">
                <span className="work-title">
                    {t.title}
                    {t.priority !== 'oddiy' && (
                        <span className={`work-badge work-badge--${t.priority}`}>{t.priority_display}</span>
                    )}
                    {t.status === 'jarayonda' && <span className="work-badge">Jarayonda</span>}
                </span>
                <span className="work-meta">
                    Kimga: <strong>{t.assigned_to_name}</strong>
                    {t.due_date && <> · Muddat: {formatDate(t.due_date)}</>}
                    {t.is_overdue && <span className="task-overdue"> · muddati o'tgan</span>}
                </span>
                {t.description && <span className="work-desc">{t.description}</span>}
                {t.status === 'bajarildi' && (
                    <span className="work-meta">
                        Bajargan: <strong>{t.completed_by_name || "noma'lum"}</strong> · {formatDate(t.completed_at)}
                        {t.result_note && <> · Izoh: {t.result_note}</>}
                    </span>
                )}
            </div>
            <div className="work-side">
                {t.status === 'yangi' && (
                    <button type="button" className="btn-ghost" onClick={() => patch(t, { status: 'jarayonda' })}>
                        Boshladim
                    </button>
                )}
                {t.status !== 'bajarildi' && (
                    <button type="button" className="btn-primary btn-auto btn-small" onClick={() => handleFinish(t)}>
                        Bajarildi
                    </button>
                )}
                {isOwner && t.status === 'bajarildi' && (
                    <button type="button" className="btn-ghost" onClick={() => patch(t, { status: 'jarayonda' })}>
                        Qayta ochish
                    </button>
                )}
                {isOwner && (
                    <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDelete(t)}>
                        O'chirish
                    </button>
                )}
            </div>
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
                        <h2 className="panel-title">{farm.name}: vazifalar</h2>
                        <p className="panel-subtitle">
                            {isOwner ? 'Ishchilarga vazifa bering va bajarilishini kuzating' : 'Sizga berilgan vazifalar'}
                        </p>

                        {isOwner && (
                            <>
                                <h3 className="section-title">Yangi vazifa</h3>
                                <div className="work-card">
                                    <form onSubmit={handleAdd}>
                                        <div className="form-field">
                                            <label>Vazifa</label>
                                            <input type="text" name="title" value={form.title} onChange={handleChange}
                                                placeholder="Masalan: Ertaga ertalab sigirlarni vaksinatsiya qiling" required />
                                        </div>
                                        <div className="form-field">
                                            <label>Izoh (ixtiyoriy)</label>
                                            <input type="text" name="description" value={form.description} onChange={handleChange} />
                                        </div>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Kimga</label>
                                                <select name="assigned_to" value={form.assigned_to} onChange={handleChange}>
                                                    <option value="">Barcha ishchilarga</option>
                                                    {workers.map((w) => (
                                                        <option key={w.id} value={w.user}>{w.user_full_name}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div className="form-field">
                                                <label>Muddat (ixtiyoriy)</label>
                                                <input type="date" name="due_date" value={form.due_date} onChange={handleChange} />
                                            </div>
                                        </div>
                                        <div className="form-field">
                                            <label>Muhimligi</label>
                                            <select name="priority" value={form.priority} onChange={handleChange}>
                                                {Object.entries(PRIORITIES).map(([v, l]) => (
                                                    <option key={v} value={v}>{l}</option>
                                                ))}
                                            </select>
                                        </div>
                                        {workers.length === 0 && (
                                            <p className="workers-hint">
                                                Fermada hali ishchi yo'q. Dashboard'dagi "Ishchilar" tugmasi orqali ishchi qo'shing.
                                            </p>
                                        )}
                                        {formError && <p className="error-text" role="alert">{formError}</p>}
                                        <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                                            {saving ? 'Kuting...' : "Vazifa berish"}
                                        </button>
                                    </form>
                                </div>

                                <div className="filter-bar">
                                    <select value={assigneeFilter} onChange={(e) => setAssigneeFilter(e.target.value)}>
                                        <option value="">Hamma ishchilar</option>
                                        <option value="all">Barcha ishchilarga berilganlar</option>
                                        {workers.map((w) => (
                                            <option key={w.id} value={w.user}>{w.user_full_name}</option>
                                        ))}
                                    </select>
                                </div>
                            </>
                        )}

                        <h3 className="section-title">Bajarilishi kerak ({open.length})</h3>
                        {open.length === 0 ? (
                            <p className="empty-state">Hozircha bajarilmagan vazifa yo'q</p>
                        ) : (
                            <ul className="work-list">{open.map(renderTask)}</ul>
                        )}

                        <h3 className="section-title">Bajarilgan ({done.length})</h3>
                        {done.length === 0 ? (
                            <p className="empty-state">Hali bajarilgan vazifa yo'q</p>
                        ) : (
                            <ul className="work-list">{done.map(renderTask)}</ul>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default Tasks;
