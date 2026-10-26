import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { Icon } from './dashboardKit';
import TreatmentPdfButton from './TreatmentPdfButton';
import './WorkerHome.css';

const asList = (d) => (Array.isArray(d) ? d : d?.results ?? []);
const pad = (n) => String(n).padStart(2, '0');

function fmt(iso) {
    if (!iso) return '';
    const [, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}`;
}

// Ishchi uchun "Bugun" ekrani: eng kerakli 4 ta amal, ochiq vazifalar va oylik davomati.
function WorkerHome({ farms, onChanged }) {
    const [tasks, setTasks] = useState([]);
    const [absent, setAbsent] = useState(0);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        api.get('tasks/', { params: { open: 1 } })
            .then(({ data }) => setTasks(asList(data)))
            .catch(() => {});
        const now = new Date();
        api.get('attendance/', { params: { month: `${now.getFullYear()}-${pad(now.getMonth() + 1)}` } })
            .then(({ data }) => setAbsent(asList(data).filter((r) => r.status === 'kelmadi').length))
            .catch(() => {});
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const sorted = [...tasks].sort((a, b) => {
        if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
        if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
        return a.due_date ? -1 : b.due_date ? 1 : 0;
    });

    const finish = async (t) => {
        const note = window.prompt('Bajarilgan ish haqida izoh (ixtiyoriy):', '');
        if (note === null) return;
        try {
            await api.patch(`tasks/${t.id}/`, { status: 'bajarildi', result_note: note.trim() });
            setError('');
            load();
            onChanged?.();
        } catch (err) {
            setError(getErrorMessage(err, "Belgilab bo'lmadi"));
        }
    };

    const multi = farms.length > 1;

    return (
        <section className="wh">
            {farms.map((farm) => (
                <div key={farm.id} className="wh-farm">
                    {multi && <h3 className="wh-farm-name">{farm.name}</h3>}
                    {farm.my_role === 'veterinar' ? (
                        <div className="wh-actions">
                            <Link className="wh-btn wh-btn--main" to={`/farms/${farm.id}/work`}>
                                <span className="wh-btn-emoji" aria-hidden="true">💉</span>
                                <span>Davolash va vaksinatsiya</span>
                            </Link>
                            <Link className="wh-btn" to={`/farms/${farm.id}/animals`}>
                                <span className="wh-btn-emoji" aria-hidden="true">🐄</span>
                                <span>Hayvonlar</span>
                            </Link>
                            <Link className="wh-btn" to={`/farms/${farm.id}/inventory`}>
                                <span className="wh-btn-emoji" aria-hidden="true">💊</span>
                                <span>Dorilar (ombor)</span>
                            </Link>
                            <p className="wh-pdf"><TreatmentPdfButton farmId={farm.id} /></p>
                        </div>
                    ) : (
                    <div className="wh-actions">
                        <Link className="wh-btn wh-btn--main" to={`/farms/${farm.id}/animals`}>
                            <span className="wh-btn-emoji" aria-hidden="true">🥛</span>
                            <span>Sut yozish</span>
                        </Link>
                        <Link className="wh-btn" to={`/farms/${farm.id}/work`}>
                            <span className="wh-btn-emoji" aria-hidden="true">💉</span>
                            <span>Davolash va ishlar</span>
                        </Link>
                        <Link className="wh-btn" to={`/farms/${farm.id}/tasks`}>
                            <span className="wh-btn-emoji" aria-hidden="true">📋</span>
                            <span>Vazifalar</span>
                        </Link>
                        <Link className="wh-btn" to={`/farms/${farm.id}/inventory`}>
                            <span className="wh-btn-emoji" aria-hidden="true">📦</span>
                            <span>Ombor</span>
                        </Link>
                    </div>
                    )}
                </div>
            ))}

            <h2 className="db-h2">Bugungi vazifalar</h2>
            {error && <p className="error-text" role="alert">{error}</p>}
            {sorted.length === 0 ? (
                <p className="db-muted">Hozircha ochiq vazifa yo'q. Ishingizga omad!</p>
            ) : (
                <ul className="wh-tasks">
                    {sorted.slice(0, 6).map((t) => (
                        <li key={t.id} className={`wh-task${t.is_overdue ? ' wh-task--late' : ''}`}>
                            <div className="wh-task-text">
                                <span className="wh-task-title">{t.title}</span>
                                <span className="wh-task-meta">
                                    {t.due_date ? `Muddat: ${fmt(t.due_date)}` : 'Muddatsiz'}
                                    {t.is_overdue && ' · muddati o\'tgan'}
                                    {t.priority !== 'oddiy' && ` · ${t.priority_display}`}
                                </span>
                            </div>
                            <button type="button" className="wh-done" onClick={() => finish(t)} aria-label={`"${t.title}" bajarildi`}>
                                <Icon name="check" size={20} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
            {sorted.length > 6 && <p className="db-muted">Yana {sorted.length - 6} ta vazifa «Vazifalar» bo'limida.</p>}

            {!farms.every((f) => f.my_role === 'veterinar') && (
                <p className="wh-attendance">
                    📅 Shu oyda kelmagan kunlaringiz: <strong>{absent}</strong>
                </p>
            )}
        </section>
    );
}

export default WorkerHome;
