import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import FarmForm from '../components/FarmForm';
import AdminPanel from '../components/AdminPanel';
import { getErrorMessage } from '../utils/errors';

const FARM_TYPES = {
    chorvachilik: 'Chorvachilik',
    parrandachilik: 'Parrandachilik',
    aralash: 'Aralash',
};

function FarmList({ farms, showFinance }) {
    return (
        <ul className="farm-list">
            {farms.map((farm) => (
                <li key={farm.id} className="farm-item">
                    <div>
                        <span className="farm-item-name">{farm.name}</span>
                        <span className="farm-item-type">{FARM_TYPES[farm.farm_type] || farm.farm_type}</span>
                    </div>
                    <div className="farm-item-side">
                        <span className="farm-item-location">{farm.location}</span>
                        {showFinance && (
                            <Link className="farm-item-link" to={`/farms/${farm.id}/finance`}>
                                Kirim-chiqim →
                            </Link>
                        )}
                    </div>
                </li>
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
        return <FarmList farms={farms} showFinance={user.role === 'fermer'} />;
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
