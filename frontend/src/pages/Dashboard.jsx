import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import FarmForm from '../components/FarmForm';
import AdminPanel from '../components/AdminPanel';
import WorkersPanel from '../components/WorkersPanel';
import FarmerOverview from '../components/FarmerOverview';
import WorkerHome from '../components/WorkerHome';
import WeatherPanel from '../components/WeatherPanel';
import TelegramBanner from '../components/TelegramBanner';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { t } from '../i18n';
import NotificationBell from '../components/NotificationBell';
import AssistantChat from '../components/AssistantChat';
import { Icon } from '../components/dashboardKit';
import { greeting, longDate } from '../utils/dashboardDates';
import './Dashboard.css';

const FARM_TYPES = {
    chorvachilik: 'Chorvachilik',
    parrandachilik: 'Parrandachilik',
    aralash: 'Aralash',
};

// Ferma ichidagi bo'limga o'tish qatori. to bo'lmasa, qator bosilmaydi (ruxsat yo'q).
// onClick berilsa, qator havola emas, ochiladigan tugma bo'ladi (expanded: ochiq yoki yo'qligi)
function FarmRow({ to, icon, title, status, alert, onClick, expanded }) {
    const body = (
        <>
            <span className="db-row-icon"><Icon name={icon} size={18} /></span>
            <span className="db-row-text">
                <span className="db-row-title">{title}</span>
                <span className="db-row-status">{status}</span>
            </span>
            {(to || onClick) && <Icon name="chevron" size={16} className="db-row-go" />}
        </>
    );
    if (onClick) {
        return (
            <button type="button" className={`db-row db-row--button${expanded ? ' is-open' : ''}`}
                onClick={onClick} aria-expanded={expanded}>
                {body}
            </button>
        );
    }
    if (!to) {
        return <div className="db-row db-row--locked" aria-disabled="true">{body}</div>;
    }
    return (
        <Link className={`db-row${alert ? ' db-row--alert' : ''}`} to={to}>
            {body}
        </Link>
    );
}

function FarmItem({ farm, showFinance, canManage, tasks, lowStock, debts, onUpdated, onDeleted }) {
    const [editing, setEditing] = useState(false);
    const [showWorkers, setShowWorkers] = useState(false);
    const [formData, setFormData] = useState({
        name: farm.name,
        location: farm.location,
        farm_type: farm.farm_type,
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    const startEdit = () => {
        setFormData({ name: farm.name, location: farm.location, farm_type: farm.farm_type });
        setError('');
        setEditing(true);
    };

    const handleChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError('');
        try {
            const { data } = await api.patch(`farms/${farm.id}/`, formData);
            onUpdated(data);
            setEditing(false);
        } catch (err) {
            setError(getErrorMessage(err, t("Fermani saqlab bo'lmadi")));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        const ok = window.confirm(
            t('"{name}" fermasini o\'chirmoqchimisiz?', { name: farm.name }) + '\n\n' +
            t("Fermaning barcha ma'lumotlari (kirim-chiqim, hayvonlar, ishchilar) ham o'chib ketadi.") + ' ' +
            t("Buni qaytarib bo'lmaydi.")
        );
        if (!ok) return;
        try {
            await api.delete(`farms/${farm.id}/`);
            onDeleted(farm.id);
        } catch (err) {
            window.alert(getErrorMessage(err, t("Fermani o'chirib bo'lmadi")));
        }
    };

    if (editing) {
        return (
            <li className="db-farm db-farm--editing">
                <form className="farm-edit-form" onSubmit={handleSave}>
                    <div className="form-field">
                        <label>{t('Nomi')}</label>
                        <input type="text" name="name" value={formData.name} onChange={handleChange} required />
                    </div>
                    <div className="form-field">
                        <label>{t('Joylashuvi')}</label>
                        <input type="text" name="location" value={formData.location} onChange={handleChange} required />
                    </div>
                    <div className="form-field">
                        <label>{t('Turi')}</label>
                        <select name="farm_type" value={formData.farm_type} onChange={handleChange}>
                            <option value="chorvachilik">{t('Chorvachilik')}</option>
                            <option value="parrandachilik">{t('Parrandachilik')}</option>
                            <option value="aralash">{t('Aralash')}</option>
                        </select>
                    </div>
                    {error && <p className="error-text">{error}</p>}
                    <div className="farm-edit-actions">
                        <button type="submit" className="btn-primary" disabled={saving}>
                            {saving ? t('Kuting...') : t('Saqlash')}
                        </button>
                        <button type="button" className="btn-ghost" onClick={() => setEditing(false)} disabled={saving}>
                            {t('Bekor qilish')}
                        </button>
                    </div>
                </form>
            </li>
        );
    }

    const taskStatus = tasks.overdue > 0
        ? t("{n} ta muddati o'tgan", { n: tasks.overdue })
        : tasks.open > 0 ? t('{n} ta ochiq', { n: tasks.open }) : t("Ochiq vazifa yo'q");
    const stockStatus = lowStock > 0 ? t('{n} ta kam qolgan', { n: lowStock }) : t('Zaxira yetarli');
    const debtStatus = !showFinance
        ? t("Ko'rishga ruxsat yo'q")
        : debts.overdue_count > 0
            ? t("{n} ta muddati o'tgan", { n: debts.overdue_count })
            : t('Kim qancha qarz');

    return (
        <li className="db-farm">
            <div className="db-farm-head">
                <div>
                    <h3 className="db-farm-name">{farm.name}</h3>
                    <p className="db-farm-place">{farm.location}</p>
                </div>
                <span className="db-farm-type">{t(FARM_TYPES[farm.farm_type]) ? t(FARM_TYPES[farm.farm_type]) : farm.farm_type}</span>
            </div>

            <div className="db-rows">
                <FarmRow
                    to={`/farms/${farm.id}/work`}
                    icon="work"
                    title={t('Ferma ishlari')}
                    status={t('Hayvonlar va davolash')}
                />
                <FarmRow
                    to={`/farms/${farm.id}/animals`}
                    icon="tag"
                    title={t('Barcha hayvonlar')}
                    status={t("Vazn, sut, tug'ish, davolash")}
                />
                <FarmRow
                    to={`/farms/${farm.id}/tasks`}
                    icon="tasks"
                    title={t('Vazifalar')}
                    status={taskStatus}
                    alert={tasks.overdue > 0}
                />
                <FarmRow
                    to={`/farms/${farm.id}/inventory`}
                    icon="stock"
                    title={t('Ombor')}
                    status={stockStatus}
                    alert={lowStock > 0}
                />
                <FarmRow
                    to={showFinance ? `/farms/${farm.id}/finance` : null}
                    icon={showFinance ? 'money' : 'lock'}
                    title={t('Kirim-chiqim')}
                    status={showFinance ? t('Hisob-kitob') : t("Ko'rishga ruxsat yo'q")}
                />
                <FarmRow
                    to={showFinance ? `/farms/${farm.id}/debts` : null}
                    icon={showFinance ? 'debt' : 'lock'}
                    title={t('Qarzlar')}
                    status={debtStatus}
                    alert={showFinance && debts.overdue_count > 0}
                />
                {canManage && (
                    <>
                        <FarmRow
                            icon="users"
                            title={t('Ishchilar')}
                            status={t("Qo'shish va ruxsatlar")}
                            onClick={() => setShowWorkers((v) => !v)}
                            expanded={showWorkers}
                        />
                        {showWorkers && <div className="db-workers"><WorkersPanel farmId={farm.id} /></div>}
                    </>
                )}
            </div>

            {canManage && (
                <div className="db-farm-actions">
                    <button type="button" className="db-link-btn" onClick={startEdit}>
                        {t('Tahrirlash')}
                    </button>
                    <button type="button" className="db-link-btn db-link-btn--danger" onClick={handleDelete}>
                        {t("O'chirish")}
                    </button>
                </div>
            )}
        </li>
    );
}

// Yangi ferma qo'shish: dastlab yig'ilgan, bosilganda forma ochiladi
function NewFarm({ onCreated, first }) {
    const [expanded, setExpanded] = useState(false);
    const open = expanded || first; // birinchi fermada forma darrov ochiq turadi
    const setOpen = setExpanded;

    if (!open) {
        return (
            <li className="db-farm db-farm--new">
                <button type="button" className="db-newfarm-btn" onClick={() => setOpen(true)}>
                    <Icon name="plus" size={22} />
                    <span>{t("Yangi ferma qo'shish")}</span>
                </button>
            </li>
        );
    }
    return (
        <li className="db-farm db-farm--form">
            <FarmForm onFarmCreated={(farm) => { onCreated(farm); setOpen(false); }} />
            {!first && (
                <button type="button" className="db-link-btn" onClick={() => setOpen(false)}>{t('Bekor qilish')}</button>
            )}
        </li>
    );
}

function FarmList({ farms, currentUsername, taskCounts, lowStockCounts, debtCounts, onUpdated, onDeleted, extra }) {
    return (
        <ul className="db-farms">
            {farms.map((farm) => (
                <FarmItem
                    key={farm.id}
                    farm={farm}
                    showFinance={farm.can_view_finance}
                    canManage={farm.owner_username === currentUsername}
                    tasks={taskCounts[farm.id] || { open: 0, overdue: 0 }}
                    lowStock={lowStockCounts[farm.id] || 0}
                    debts={debtCounts[farm.id] || { overdue_count: 0 }}
                    onUpdated={onUpdated}
                    onDeleted={onDeleted}
                />
            ))}
            {extra}
        </ul>
    );
}

function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [farms, setFarms] = useState([]);
    const [taskCounts, setTaskCounts] = useState({});
    const [lowStockCounts, setLowStockCounts] = useState({});
    const [debtCounts, setDebtCounts] = useState({});
    const [dataVersion, setDataVersion] = useState(0); // AI amal bajargach oshadi: raqamlar qayta yuklanadi
    const isAdmin = user.role === 'admin';
    const [loading, setLoading] = useState(!isAdmin);
    const [error, setError] = useState('');

    const fetchFarms = useCallback(async () => {
        try {
            const { data } = await api.get('farms/');
            // DRF pagination yoqilsa { results: [...] } qaytadi
            setFarms(Array.isArray(data) ? data : data.results ?? []);
            setError('');
        } catch (err) {
            setError(getErrorMessage(err, t("Fermalarni yuklab bo'lmadi")));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // admin fermalarni AdminPanel ichida yuklaydi
        if (!isAdmin) fetchFarms();
    }, [fetchFarms, isAdmin]);

    // Bajarilmagan vazifalar soni (har bir ferma uchun)
    useEffect(() => {
        if (isAdmin) return;
        let cancelled = false;
        api.get('tasks/', { params: { open: 1 } })
            .then(({ data }) => {
                if (cancelled) return;
                const list = Array.isArray(data) ? data : data.results ?? [];
                const counts = {};
                list.forEach((task) => {
                    const c = counts[task.farm] || (counts[task.farm] = { open: 0, overdue: 0 });
                    c.open += 1;
                    if (task.is_overdue) c.overdue += 1;
                });
                setTaskCounts(counts);
            })
            .catch(() => {}); // sanagich ko'rinmasa ham asosiy sahifa ishlayveradi
        return () => {
            cancelled = true;
        };
    }, [isAdmin, dataVersion]);

    // Zaxirasi kam qolgan mahsulotlar soni (har bir ferma uchun)
    useEffect(() => {
        if (isAdmin) return;
        let cancelled = false;
        api.get('inventory-item/', { params: { low: 1 } })
            .then(({ data }) => {
                if (cancelled) return;
                const list = Array.isArray(data) ? data : data.results ?? [];
                const counts = {};
                list.forEach((i) => {
                    counts[i.farm] = (counts[i.farm] || 0) + 1;
                });
                setLowStockCounts(counts);
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [isAdmin, dataVersion]);

    // Muddati o'tgan qarzlar soni (moliya huquqi bor fermalar uchun)
    useEffect(() => {
        if (isAdmin) return;
        let cancelled = false;
        api.get('debt/overview/')
            .then(({ data }) => {
                if (cancelled) return;
                const counts = {};
                (Array.isArray(data) ? data : []).forEach((r) => {
                    counts[r.farm] = r;
                });
                setDebtCounts(counts);
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [isAdmin, dataVersion]);

    const handleRetry = () => {
        setLoading(true);
        fetchFarms();
    };

    const handleLogout = () => {
        logout();
        navigate('/login', { replace: true });
    };

    const handleFarmCreated = (newFarm) => {
        setFarms((prev) => [newFarm, ...prev]);
    };

    const handleFarmUpdated = (updated) => {
        setFarms((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
    };

    const handleFarmDeleted = (id) => {
        setFarms((prev) => prev.filter((f) => f.id !== id));
    };

    const renderFarms = () => {
        if (loading) return <p className="db-muted">{t('Yuklanmoqda...')}</p>;
        if (error) {
            return (
                <div className="db-muted">
                    <p className="error-text">{error}</p>
                    <button className="btn-ghost" onClick={handleRetry}>{t('Qayta urinish')}</button>
                </div>
            );
        }
        return (
            <FarmList
                farms={farms}
                currentUsername={user.username}
                taskCounts={taskCounts}
                lowStockCounts={lowStockCounts}
                debtCounts={debtCounts}
                onUpdated={handleFarmUpdated}
                onDeleted={handleFarmDeleted}
                extra={user.role === 'fermer' ? <NewFarm onCreated={handleFarmCreated} first={farms.length === 0} /> : null}
            />
        );
    };

    const openTasks = Object.values(taskCounts).reduce((s, c) => s + c.open, 0);
    const lateTasks = Object.values(taskCounts).reduce((s, c) => s + c.overdue, 0);

    const farmsSection = (
        <>
            {!loading && !error && farms.length > 0 && <WeatherPanel farms={farms} />}
            <section className="db-section">
                <h2 className="db-h2">{user.role === 'fermer' ? t('Mening fermalarim') : t('Sizning fermalaringiz')}</h2>
                {renderFarms()}
            </section>
        </>
    );

    return (
        <div className="app-shell db-page">
            <header className="app-header">
                <h1>{t('FarmLine')}</h1>
                <div className="user-bar">
                    <span>{t('Salom, {name}!', { name: user.first_name || user.username })}</span>
                    <LanguageSwitcher />
                    <NotificationBell />
                    <Link to="/profile" className="user-link">{t('Profil')}</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={handleLogout}>{t('Chiqish')}</button>
                </div>
            </header>

            {user.role === 'admin' && (
                <main className="app-main">
                    <TelegramBanner />
                    <div className="panel">
                        <h2 className="panel-title">{t('Admin Panel')}</h2>
                        <p className="panel-subtitle">{t('Barcha fermerlar va ularning fermalari')}</p>
                        <AdminPanel />
                    </div>
                </main>
            )}

            {user.role === 'fermer' && (
                <FarmerOverview refreshKey={`${farms.length}-${dataVersion}`}>
                    <TelegramBanner />
                    {farmsSection}
                </FarmerOverview>
            )}

            {user.role === 'ishchi' && (
                <>
                    <section className="db-hero">
                        <div className="db-hero-inner">
                            <div className="db-hero-main">
                                <p className="db-date">{longDate()}</p>
                                <h2 className="db-hello">{greeting()}, {user.first_name || user.username}</h2>
                                <p className="db-hero-note">
                                    {openTasks === 0
                                        ? t("Sizga tayinlangan ochiq vazifa yo'q.")
                                        : t('Sizda {n} ta ochiq vazifa bor', { n: openTasks }) +
                                            (lateTasks > 0 ? t(", {n} tasining muddati o'tgan", { n: lateTasks }) : '') + '.'}
                                </p>
                            </div>
                        </div>
                    </section>
                    <div className="db-main">
                        {!loading && !error && farms.length > 0 && (<WorkerHome farms={farms} onChanged={() => setDataVersion((v) => v + 1)} />)}
                        {farms.length > 0 ? (<details className="more-menu"><summary className="db-h2">{t("Boshqa bo'limlar")}</summary>{farmsSection}</details>) : farmsSection}
                    </div>
                </>
            )}
            <AssistantChat onActionDone={() => setDataVersion((v) => v + 1)} />
        </div>
    );
}

export default Dashboard;
