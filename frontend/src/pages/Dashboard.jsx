import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import FarmForm from '../components/FarmForm';
import AdminPanel from '../components/AdminPanel';
import WorkersPanel from '../components/WorkersPanel';
import { getErrorMessage } from '../utils/errors';

const FARM_TYPES = {
    chorvachilik: 'Chorvachilik',
    parrandachilik: 'Parrandachilik',
    aralash: 'Aralash',
};

function FarmItem({ farm, showFinance, canManage, onUpdated, onDeleted }) {
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

    return (
        <li className="farm-item">
            <div>
                <span className="farm-item-name">{farm.name}</span>
                <span className="farm-item-type">{FARM_TYPES[farm.farm_type] || farm.farm_type}</span>
            </div>
            <div className="farm-item-side">
                <span className="farm-item-location">{farm.location}</span>
                <Link className="farm-item-link" to={`/farms/${farm.id}/work`}>
                    Ferma ishlari →
                </Link>
                {showFinance ? (
                    <Link className="farm-item-link" to={`/farms/${farm.id}/finance`}>
                        Kirim-chiqim →
                    </Link>
                ) : (
                    <span className="farm-item-note">Kirim-chiqimni ko'rishga ruxsat yo'q</span>
                )}
                {canManage && (
                    <div className="farm-item-actions">
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
            </div>
            {canManage && showWorkers && <WorkersPanel farmId={farm.id} />}
        </li>
    );
}

function FarmList({ farms, currentUsername, onUpdated, onDeleted }) {
    return (
        <ul className="farm-list">
            {farms.map((farm) => (
                <FarmItem
                    key={farm.id}
                    farm={farm}
                    showFinance={farm.can_view_finance}
                    canManage={farm.owner_username === currentUsername}
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
                    <button className="btn-ghost" onClick={handleLogout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                {user.role === 'admin' && (
                    <div className="panel">
                        <h2 className="panel-title">Admin Panel</h2>
                        <p className="panel-subtitle">Barcha fermerlar va ularning fermalari</p>
                        <AdminPanel />
                    </div>
                )}

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
        </div>
    );
}

export default Dashboard;
