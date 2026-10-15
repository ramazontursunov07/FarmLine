import { useState, useEffect, useMemo } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import InstallButton from '../components/InstallButton';

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
    }, [farmId]);

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
                    </>
                )}
            </main>
        </div>
    );
}

export default AnimalCards;
