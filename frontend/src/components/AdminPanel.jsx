import { useState, useEffect, useMemo, useCallback } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const FARM_TYPES = {
    chorvachilik: 'Chorvachilik',
    parrandachilik: 'Parrandachilik',
    aralash: 'Aralash',
};

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

function fullName(u) {
    return [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username;
}

function AdminPanel() {
    const [farmers, setFarmers] = useState([]);
    const [farms, setFarms] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [search, setSearch] = useState('');
    const [openId, setOpenId] = useState(null);

    const load = useCallback(async () => {
        try {
            const [usersRes, farmsRes] = await Promise.all([
                api.get('users/list/', { params: { role: 'fermer' } }),
                api.get('farms/'),
            ]);
            setFarmers(asList(usersRes.data));
            setFarms(asList(farmsRes.data));
            setError('');
        } catch (err) {
            setError(getErrorMessage(err, "Ma'lumotlarni yuklab bo'lmadi"));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const handleRetry = () => {
        setLoading(true);
        load();
    };

    const farmsByOwner = useMemo(() => {
        const map = new Map();
        farms.forEach((f) => {
            if (!map.has(f.owner)) map.set(f.owner, []);
            map.get(f.owner).push(f);
        });
        return map;
    }, [farms]);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return farmers;
        return farmers.filter((u) =>
            [u.username, u.first_name, u.last_name, u.phone_number, u.email]
                .filter(Boolean)
                .some((v) => v.toLowerCase().includes(q))
        );
    }, [farmers, search]);

    if (loading) return <p className="empty-state">Yuklanmoqda...</p>;

    if (error) {
        return (
            <div className="empty-state">
                <p className="error-text">{error}</p>
                <button className="btn-ghost" onClick={handleRetry}>Qayta urinish</button>
            </div>
        );
    }

    return (
        <>
            <div className="stat-grid">
                <div className="stat-card">
                    <span className="stat-value">{farmers.length}</span>
                    <span className="stat-label">Fermerlar</span>
                </div>
                <div className="stat-card">
                    <span className="stat-value">{farms.length}</span>
                    <span className="stat-label">Fermalar</span>
                </div>
            </div>

            <h3 className="section-title">Fermerlar</h3>

            <input
                type="search"
                className="search-input"
                placeholder="Ism, username yoki telefon bo'yicha qidirish"
                aria-label="Fermerlarni qidirish"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
            />

            {filtered.length === 0 ? (
                <p className="empty-state">
                    {farmers.length === 0 ? "Hali fermerlar yo'q" : 'Hech narsa topilmadi'}
                </p>
            ) : (
                <ul className="farmer-list">
                    {filtered.map((u) => {
                        const userFarms = farmsByOwner.get(u.id) ?? [];
                        const isOpen = openId === u.id;
                        return (
                            <li key={u.id} className="farmer-item">
                                <button
                                    type="button"
                                    className="farmer-head"
                                    onClick={() => setOpenId(isOpen ? null : u.id)}
                                    aria-expanded={isOpen}
                                >
                                    <span>
                                        <span className="farmer-name">{fullName(u)}</span>
                                        <span className="farmer-meta">
                                            @{u.username}
                                            {u.phone_number ? ` · ${u.phone_number}` : ''}
                                        </span>
                                    </span>
                                    <span className="farmer-count">{userFarms.length} ta ferma</span>
                                </button>

                                {isOpen && (
                                    <div className="farmer-body">
                                        {userFarms.length === 0 ? (
                                            <p className="farmer-empty">Hali ferma qo'shmagan</p>
                                        ) : (
                                            <ul className="farm-list farm-list--inner">
                                                {userFarms.map((farm) => (
                                                    <li key={farm.id} className="farm-item">
                                                        <div>
                                                            <span className="farm-item-name">{farm.name}</span>
                                                            <span className="farm-item-type">
                                                                {FARM_TYPES[farm.farm_type] || farm.farm_type}
                                                            </span>
                                                        </div>
                                                        <span className="farm-item-location">{farm.location}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </>
    );
}

export default AdminPanel;
