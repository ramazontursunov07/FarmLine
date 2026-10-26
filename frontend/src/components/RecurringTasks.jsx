import { useEffect, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const FREQ = { kunlik: 'Har kuni', haftalik: 'Har hafta', oylik: 'Har oy', yillik: 'Har yili' };
const EMPTY = { title: '', assigned_to: '', frequency: 'yillik', next_due: '', lead_days: 3, priority: 'oddiy' };

// Tez to'ldirish uchun tayyor namunalar
const PRESETS = [
    { label: 'Vaksinatsiya (yiliga)', title: 'Qoramollarni vaksinatsiya qilish', frequency: 'yillik', priority: 'muhim', lead_days: 7 },
    { label: 'Mollarni tortish (oyiga)', title: "Mollarni tortib, vazn yozish", frequency: 'oylik', priority: 'oddiy', lead_days: 1 },
    { label: 'Chorva hovlisini tozalash (haftasiga)', title: 'Chorva hovlisini tozalash', frequency: 'haftalik', priority: 'oddiy', lead_days: 0 },
];

const asList = (d) => (Array.isArray(d) ? d : d?.results ?? []);

function fmt(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function RecurringTasks({ farmId, workers, onCreated }) {
    const [items, setItems] = useState([]);
    const [form, setForm] = useState(EMPTY);
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);
    const [key, setKey] = useState(0);

    useEffect(() => {
        let cancelled = false;
        api.get('tasks-recurring/', { params: { farm: farmId } })
            .then((r) => { if (!cancelled) setItems(asList(r.data)); })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [farmId, key]);

    const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError('');
        try {
            await api.post('tasks-recurring/', {
                farm: Number(farmId),
                title: form.title,
                assigned_to: form.assigned_to ? Number(form.assigned_to) : null,
                frequency: form.frequency,
                next_due: form.next_due,
                lead_days: Number(form.lead_days) || 0,
                priority: form.priority,
            });
            setForm(EMPTY);
            setKey((k) => k + 1);
            onCreated?.();
        } catch (err) {
            setError(getErrorMessage(err, "Saqlab bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const toggle = async (it) => {
        try {
            await api.patch(`tasks-recurring/${it.id}/`, { is_active: !it.is_active });
            setKey((k) => k + 1);
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const remove = async (it) => {
        if (!window.confirm(`"${it.title}" takrorlanuvchi vazifasini o'chirasizmi?`)) return;
        try {
            await api.delete(`tasks-recurring/${it.id}/`);
            setKey((k) => k + 1);
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    return (
        <details className="more-menu">
            <summary className="section-title">🔁 Takrorlanuvchi vazifalar ({items.length})</summary>
            <div className="work-card">
                <p className="panel-subtitle">
                    Masalan, har yili vaksina yoki har oy tortish. Muddat kelganda vazifa o'zi yaratiladi va ishchiga Telegramdan xabar boradi.
                </p>
                <div className="filter-bar">
                    {PRESETS.map((p) => (
                        <button key={p.label} type="button" className="btn-ghost"
                            onClick={() => setForm({ ...form, title: p.title, frequency: p.frequency, priority: p.priority, lead_days: p.lead_days })}>
                            {p.label}
                        </button>
                    ))}
                </div>
                <form onSubmit={submit}>
                    <div className="form-field">
                        <label>Vazifa</label>
                        <input type="text" name="title" value={form.title} onChange={change} required />
                    </div>
                    <div className="form-row">
                        <div className="form-field">
                            <label>Qanchalik tez-tez</label>
                            <select name="frequency" value={form.frequency} onChange={change}>
                                {Object.entries(FREQ).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                        </div>
                        <div className="form-field">
                            <label>Birinchi muddat</label>
                            <input type="date" name="next_due" value={form.next_due} onChange={change} required />
                        </div>
                    </div>
                    <div className="form-row">
                        <div className="form-field">
                            <label>Kimga</label>
                            <select name="assigned_to" value={form.assigned_to} onChange={change}>
                                <option value="">Barcha ishchilarga</option>
                                {workers.map((w) => <option key={w.id} value={w.user}>{w.user_full_name}</option>)}
                            </select>
                        </div>
                        <div className="form-field">
                            <label>Necha kun oldin eslatilsin</label>
                            <input type="number" min="0" max="60" name="lead_days" value={form.lead_days} onChange={change} />
                        </div>
                    </div>
                    {error && <p className="error-text" role="alert">{error}</p>}
                    <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                        {saving ? 'Kuting...' : "Qo'shish"}
                    </button>
                </form>
            </div>

            {items.length > 0 && (
                <ul className="work-list">
                    {items.map((it) => (
                        <li key={it.id} className="work-item">
                            <div className="work-main">
                                <span className="work-title">
                                    {it.title}
                                    {!it.is_active && <span className="work-badge">To'xtatilgan</span>}
                                </span>
                                <span className="work-meta">
                                    {it.frequency_display} · keyingisi: <strong>{fmt(it.next_due)}</strong> · Kimga: {it.assigned_to_name}
                                </span>
                            </div>
                            <div className="work-side">
                                <button type="button" className="btn-ghost" onClick={() => toggle(it)}>
                                    {it.is_active ? "To'xtatish" : 'Yoqish'}
                                </button>
                                <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => remove(it)}>
                                    O'chirish
                                </button>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </details>
    );
}

export default RecurringTasks;
