import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';
import LanguageSwitcher from '../components/LanguageSwitcher';
import NotificationBell from '../components/NotificationBell';
import RecurringTasks from '../components/RecurringTasks';
import { t } from '../i18n';

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
                const requests = [api.get('tasks/', { params: { farm: farmId, limit: 300 } })];
                if (owner) requests.push(api.get('workers/', { params: { farm: farmId } }));
                const [tasksRes, workersRes] = await Promise.all(requests);
                if (cancelled) return;
                setFarm(farmRes.data);
                setTasks(asList(tasksRes.data));
                setWorkers(workersRes ? asList(workersRes.data) : []);
                setError('');
            } catch (err) {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? t('Ferma topilmadi') : getErrorMessage(err, t('Vazifalarni yuklab bo\'lmadi')));
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
        () => tasks.filter((tk) => !assigneeFilter || (assigneeFilter === 'all' ? !tk.assigned_to : String(tk.assigned_to) === assigneeFilter)),
        [tasks, assigneeFilter]
    );

    // Bajarilmaganlar: muddati o'tganlar birinchi, keyin muddati yaqinlari, muddatsizlar oxirida
    const open = useMemo(
        () =>
            visible
                .filter((tk) => tk.status !== 'bajarildi')
                .sort((a, b) => {
                    if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
                    if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
                    if (a.due_date) return -1;
                    if (b.due_date) return 1;
                    return 0;
                }),
        [visible]
    );
    const done = useMemo(() => visible.filter((tk) => tk.status === 'bajarildi'), [visible]);

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
            setFormError(getErrorMessage(err, t('Vazifani saqlab bo\'lmadi')));
        } finally {
            setSaving(false);
        }
    };

    const patch = async (task, data) => {
        try {
            await api.patch(`tasks/${task.id}/`, data);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, t('O\'zgartirib bo\'lmadi')));
        }
    };

    const handleFinish = (task) => {
        const note = window.prompt(t('Bajarilgan ish haqida izoh (ixtiyoriy):'), '');
        if (note === null) return; // Bekor qilindi
        patch(task, { status: 'bajarildi', result_note: note.trim() });
    };

    const handleDelete = async (task) => {
        if (!window.confirm(t('"{title}" vazifasini o\'chirasizmi?', { title: task.title }))) return;
        try {
            await api.delete(`tasks/${task.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, t('O\'chirib bo\'lmadi')));
        }
    };

    const renderTask = (tk) => (
        <li key={tk.id} className={`work-item work-item--${tk.status}${tk.is_overdue ? ' work-item--overdue' : ''}`}>
            <div className="work-main">
                <span className="work-title">
                    {tk.title}
                    {tk.priority !== 'oddiy' && (
                        <span className={`work-badge work-badge--${tk.priority}`}>{tk.priority_display}</span>
                    )}
                    {tk.status === 'jarayonda' && <span className="work-badge">{t('Jarayonda')}</span>}
                </span>
                <span className="work-meta">
                    {t('Kimga:')} <strong>{tk.assigned_to_name}</strong>
                    {tk.due_date && <> {t('· Muddat:')} {formatDate(tk.due_date)}</>}
                    {tk.is_overdue && <span className="task-overdue"> {t('· muddati o\'tgan')}</span>}
                </span>
                {tk.description && <span className="work-desc">{tk.description}</span>}
                {tk.status === 'bajarildi' && (
                    <span className="work-meta">
                        {t('Bajargan:')} <strong>{tk.completed_by_name || t('noma\'lum')}</strong> · {formatDate(tk.completed_at)}
                        {tk.result_note && <> {t('· Izoh:')} {tk.result_note}</>}
                    </span>
                )}
            </div>
            <div className="work-side">
                {tk.status === 'yangi' && (
                    <button type="button" className="btn-ghost" onClick={() => patch(tk, { status: 'jarayonda' })}>
                        {t('Boshladim')}
                    </button>
                )}
                {tk.status !== 'bajarildi' && (
                    <button type="button" className="btn-primary btn-auto btn-small" onClick={() => handleFinish(tk)}>
                        {t('Bajarildi')}
                    </button>
                )}
                {isOwner && tk.status === 'bajarildi' && (
                    <button type="button" className="btn-ghost" onClick={() => patch(tk, { status: 'jarayonda' })}>
                        {t('Qayta ochish')}
                    </button>
                )}
                {isOwner && (
                    <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDelete(tk)}>
                        {t('O\'chirish')}
                    </button>
                )}
            </div>
        </li>
    );

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>{t('FarmLine')}</h1>
                <div className="user-bar">
                    <span>{t('Salom,')} {user.first_name || user.username}!</span>
                    <LanguageSwitcher />
                    <NotificationBell />
                    <Link to="/profile" className="user-link">{t('Profil')}</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={logout}>{t('Chiqish')}</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">{t('← Fermalarga qaytish')}</Link>

                {loading ? (
                    <p className="empty-state">{t('Yuklanmoqda...')}</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm.name}{t(': vazifalar')}</h2>
                        <p className="panel-subtitle">
                            {isOwner ? t('Ishchilarga vazifa bering va bajarilishini kuzating') : t('Sizga berilgan vazifalar')}
                        </p>

                        {isOwner && (
                            <>
                                <h3 className="section-title">{t('Yangi vazifa')}</h3>
                                <div className="work-card">
                                    <form onSubmit={handleAdd}>
                                        <div className="form-field">
                                            <label>{t('Vazifa')}</label>
                                            <input type="text" name="title" value={form.title} onChange={handleChange}
                                                placeholder={t('Masalan: Ertaga ertalab sigirlarni vaksinatsiya qiling')} required />
                                        </div>
                                        <div className="form-field">
                                            <label>{t('Izoh (ixtiyoriy)')}</label>
                                            <input type="text" name="description" value={form.description} onChange={handleChange} />
                                        </div>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>{t('Kimga')}</label>
                                                <select name="assigned_to" value={form.assigned_to} onChange={handleChange}>
                                                    <option value="">{t('Barcha ishchilarga')}</option>
                                                    {workers.map((w) => (
                                                        <option key={w.id} value={w.user}>{w.user_full_name}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div className="form-field">
                                                <label>{t('Muddat (ixtiyoriy)')}</label>
                                                <input type="date" name="due_date" value={form.due_date} onChange={handleChange} />
                                            </div>
                                        </div>
                                        <div className="form-field">
                                            <label>{t('Muhimligi')}</label>
                                            <select name="priority" value={form.priority} onChange={handleChange}>
                                                {Object.entries(PRIORITIES).map(([k, v]) => [k, t(v)]).map(([v, l]) => (
                                                    <option key={v} value={v}>{l}</option>
                                                ))}
                                            </select>
                                        </div>
                                        {workers.length === 0 && (
                                            <p className="workers-hint">
                                                {t('Fermada hali ishchi yo\'q. Dashboard\'dagi "Ishchilar" tugmasi orqali ishchi qo\'shing.')}
                                            </p>
                                        )}
                                        {formError && <p className="error-text" role="alert">{formError}</p>}
                                        <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                                            {saving ? 'Kuting...' : t('Vazifa berish')}
                                        </button>
                                    </form>
                                </div>

                                <RecurringTasks farmId={farmId} workers={workers} onCreated={reload} />

                                <div className="filter-bar">
                                    <select value={assigneeFilter} onChange={(e) => setAssigneeFilter(e.target.value)}>
                                        <option value="">{t('Hamma ishchilar')}</option>
                                        <option value="all">{t('Barcha ishchilarga berilganlar')}</option>
                                        {workers.map((w) => (
                                            <option key={w.id} value={w.user}>{w.user_full_name}</option>
                                        ))}
                                    </select>
                                </div>
                            </>
                        )}

                        <h3 className="section-title">{t('Bajarilishi kerak (')}{open.length})</h3>
                        {open.length === 0 ? (
                            <p className="empty-state">{t('Hozircha bajarilmagan vazifa yo\'q')}</p>
                        ) : (
                            <ul className="work-list">{open.map(renderTask)}</ul>
                        )}

                        <h3 className="section-title">{t('Bajarilgan (')}{done.length})</h3>
                        {done.length === 0 ? (
                            <p className="empty-state">{t('Hali bajarilgan vazifa yo\'q')}</p>
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
