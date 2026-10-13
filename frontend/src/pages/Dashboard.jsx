import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import FarmForm from '../components/FarmForm';
import AdminPanel from '../components/AdminPanel';
import WorkersPanel from '../components/WorkersPanel';
import FarmerOverview from '../components/FarmerOverview';
import TelegramBanner from '../components/TelegramBanner';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';
import AssistantChat from '../components/AssistantChat';

const FARM_TYPES = {
    chorvachilik: 'Chorvachilik',
    parrandachilik: 'Parrandachilik',
    aralash: 'Aralash',
};

const ICONS = {
    work: (
        <path d="M5 4h11l3 3v13H5V4zm3 6h8M8 14h8M8 18h5" />
    ),
    tasks: (
        <path d="M4 6l2 2 3-3M4 14l2 2 3-3M12 7h8M12 15h8" />
    ),
    stock: (
        <path d="M3 8l9-4 9 4-9 4-9-4zm0 0v8l9 4 9-4V8M12 12v8" />
    ),
    money: (
        <path d="M3 7h18v12H3V7zm0 4h18M16 15h2" />
    ),
    lock: (
        <path d="M6 11h12v9H6v-9zm3 0V8a3 3 0 016 0v3" />
    ),
};

function TileIcon({ name }) {
    return (
        <svg className="farm-tile-icon" viewBox="0 0 24 24" width="22" height="22" fill="none"
            stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {ICONS[name]}
        </svg>
    );
}

// Ferma ichidagi bo'limga o'tish kartochkasi. to bo'lmasa, kartochka bosilmaydi (ruxsat yo'q).
function FarmTile({ to, icon, title, status, alert }) {
    const body = (
        <>
            <TileIcon name={icon} />
            <span className="farm-tile-title">{title}</span>
            <span className={`farm-tile-status${alert ? ' farm-tile-status--alert' : ''}`}>{status}</span>
        </>
    );
    if (!to) {
        return <div className="farm-tile farm-tile--locked" aria-disabled="true">{body}</div>;
    }
    return (
        <Link className={`farm-tile${alert ? ' farm-tile--alert' : ''}`} to={to}>
            {body}
        </Link>
    );
}

function FarmItem({ farm, showFinance, canManage, tasks, lowStock, onUpdated, onDeleted }) {
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
            setError(getErrorMessage(err, "Fermani saqlab bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        const ok = window.confirm(
            `"${farm.name}" fermasini o'chirmoqchimisiz?\n\n` +
            "Fermaning barcha ma'lumotlari (kirim-chiqim, hayvonlar, ishchilar) ham o'chib ketadi. " +
            "Buni qaytarib bo'lmaydi."
        );
        if (!ok) return;
        try {
            await api.delete(`farms/${farm.id}/`);
            onDeleted(farm.id);
        } catch (err) {
            window.alert(getErrorMessage(err, "Fermani o'chirib bo'lmadi"));
        }
    };

    if (editing) {
        return (
            <li className="farm-item farm-item--editing">
                <form className="farm-edit-form" onSubmit={handleSave}>
                    <div className="form-field">
                        <label>Nomi</label>
                        <input type="text" name="name" value={formData.name} onChange={handleChange} required />
                    </div>
                    <div className="form-field">
                        <label>Joylashuvi</label>
                        <input type="text" name="location" value={formData.location} onChange={handleChange} required />
                    </div>
                    <div className="form-field">
                        <label>Turi</label>
                        <select name="farm_type" value={formData.farm_type} onChange={handleChange}>
                            <option value="chorvachilik">Chorvachilik</option>
                            <option value="parrandachilik">Parrandachilik</option>
                            <option value="aralash">Aralash</option>
                        </select>
                    </div>
                    {error && <p className="error-text">{error}</p>}
                    <div className="farm-edit-actions">
                        <button type="submit" className="btn-primary" disabled={saving}>
                            {saving ? 'Kuting...' : 'Saqlash'}
                        </button>
                        <button type="button" className="btn-ghost" onClick={() => setEditing(false)} disabled={saving}>
                            Bekor qilish
                        </button>
                    </div>
                </form>
            </li>
        );
    }

    const taskStatus = tasks.overdue > 0
        ? `${tasks.overdue} ta muddati o'tgan`
        : tasks.open > 0 ? `${tasks.open} ta ochiq` : "Ochiq vazifa yo'q";
    const stockStatus = lowStock > 0 ? `${lowStock} ta kam qolgan` : 'Zaxira yetarli';

    return (
        <li className="farm-card">
            <div className="farm-card-head">
                <div>
                    <span className="farm-card-name">{farm.name}</span>
                    <span className="farm-card-location">{farm.location}</span>
                </div>
                <span className="farm-item-type">{FARM_TYPES[farm.farm_type] || farm.farm_type}</span>
            </div>

            <div className="farm-tiles">
                <FarmTile
                    to={`/farms/${farm.id}/work`}
                    icon="work"
                    title="Ferma ishlari"
                    status="Hayvonlar va davolash"
                />
                <FarmTile
                    to={`/farms/${farm.id}/tasks`}
                    icon="tasks"
                    title="Vazifalar"
                    status={taskStatus}
                    alert={tasks.overdue > 0}
                />
                <FarmTile
                    to={`/farms/${farm.id}/inventory`}
                    icon="stock"
                    title="Ombor"
                    status={stockStatus}
                    alert={lowStock > 0}
                />
                <FarmTile
                    to={showFinance ? `/farms/${farm.id}/finance` : null}
                    icon={showFinance ? 'money' : 'lock'}
                    title="Kirim-chiqim"
                    status={showFinance ? 'Hisob-kitob' : "Ko'rishga ruxsat yo'q"}
                />
            </div>

            {canManage && (
                <div className="farm-card-actions">
                    <button type="button" className="farm-item-action" onClick={() => setShowWorkers((v) => !v)}>
                        {showWorkers ? 'Ishchilarni yopish' : 'Ishchilar'}
                    </button>
                    <button type="button" className="farm-item-action" onClick={startEdit}>
                        Tahrirlash
                    </button>
                    <button type="button" className="farm-item-action farm-item-action--danger" onClick={handleDelete}>
                        O'chirish
                    </button>
                </div>
            )}
            {canManage && showWorkers && <WorkersPanel farmId={farm.id} />}
        </li>
    );
}

function FarmList({ farms, currentUsername, taskCounts, lowStockCounts, onUpdated, onDeleted }) {
    return (
        <ul className="farm-list">
            {farms.map((farm) => (
                <FarmItem
                    key={farm.id}
                    farm={farm}
                    showFinance={farm.can_view_finance}
                    canManage={farm.owner_username === currentUsername}
                    tasks={taskCounts[farm.id] || { open: 0, overdue: 0 }}
                    lowStock={lowStockCounts[farm.id] || 0}
                    onUpdated={onUpdated}
                    onDeleted={onDeleted}
                />
            ))}
        </ul>
    );
}

function Dashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [farms, setFarms] = useState([]);
    const [taskCounts, setTaskCounts] = useState({});
    const [lowStockCounts, setLowStockCounts] = useState({});
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
            setError(getErrorMessage(err, "Fermalarni yuklab bo'lmadi"));
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
                list.forEach((t) => {
                    const c = counts[t.farm] || (counts[t.farm] = { open: 0, overdue: 0 });
                    c.open += 1;
                    if (t.is_overdue) c.overdue += 1;
                });
                setTaskCounts(counts);
            })
            .catch(() => {}); // sanagich ko'rinmasa ham asosiy sahifa ishlayveradi
        return () => {
            cancelled = true;
        };
    }, [isAdmin]);

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
    }, [isAdmin]);

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
        if (loading) return <p className="empty-state">Yuklanmoqda...</p>;
        if (error) {
            return (
                <div className="empty-state">
                    <p className="error-text">{error}</p>
                    <button className="btn-ghost" onClick={handleRetry}>Qayta urinish</button>
                </div>
            );
        }
        if (farms.length === 0) return <p className="empty-state">Hali fermangiz yo'q</p>;
        return (
            <FarmList
                farms={farms}
                currentUsername={user.username}
                taskCounts={taskCounts}
                lowStockCounts={lowStockCounts}
                onUpdated={handleFarmUpdated}
                onDeleted={handleFarmDeleted}
            />
        );
    };

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <Link to="/profile" className="user-link">Profil</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={handleLogout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <TelegramBanner />

                {user.role === 'admin' && (
                    <div className="panel">
                        <h2 className="panel-title">Admin Panel</h2>
                        <p className="panel-subtitle">Barcha fermerlar va ularning fermalari</p>
                        <AdminPanel />
                    </div>
                )}

                {user.role === 'fermer' && <FarmerOverview refreshKey={farms.length} />}

                {user.role === 'fermer' && (
                    <div className="panel">
                        <h2 className="panel-title">Mening fermalarim</h2>
                        <FarmForm onFarmCreated={handleFarmCreated} />
                        {renderFarms()}
                    </div>
                )}

                {user.role === 'ishchi' && (
                    <div className="panel">
                        <h2 className="panel-title">Ish paneli</h2>
                        <p className="panel-subtitle">Sizga tayinlangan fermalar</p>
                        {renderFarms()}
                    </div>
                )}
            </main>
            <AssistantChat />
        </div>
    );
}

export default Dashboard;
