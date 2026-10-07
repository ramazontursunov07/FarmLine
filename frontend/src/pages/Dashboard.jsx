import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import FarmForm from '../components/FarmForm';
import AdminPanel from '../components/AdminPanel';

function Dashboard() {
    const { user, logout } = useAuth();
    const [farms, setFarms] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchFarms = async () => {
            try {
                const response = await api.get('farms/');
                setFarms(response.data);
            } catch (error) {
                console.error(error);
            } finally {
                setLoading(false);
            }
        };

        fetchFarms();
    }, []);

    const handleLogout = () => {
        logout();
    };

    const handleFarmCreated = (newFarm) => {
        setFarms([...farms, newFarm]);
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
                        {loading ? (
                            <p className="empty-state">Yuklanmoqda...</p>
                        ) : farms.length === 0 ? (
                            <p className="empty-state">Hali fermangiz yo'q</p>
                        ) : (
                            <ul className="farm-list">
                                {farms.map((farm) => (
                                    <li key={farm.id} className="farm-item">
                                        <span className="farm-item-name">{farm.name}</span>
                                        <span className="farm-item-location">{farm.location}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}

                {user.role === 'ishchi' && (
                    <div className="panel">
                        <h2 className="panel-title">Ish paneli</h2>
                        <p className="panel-subtitle">Sizga tayinlangan ferma ma'lumotlari shu yerda bo'ladi</p>
                    </div>
                )}
            </main>
        </div>
    );
}

export default Dashboard;
