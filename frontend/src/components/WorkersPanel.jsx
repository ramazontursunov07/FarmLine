import { useState, useEffect, useCallback } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const EMPTY_FORM = {
    first_name: '',
    last_name: '',
    username: '',
    phone_number: '',
    password: '',
    can_view_finance: false,
};

function WorkersPanel({ farmId }) {
    const [workers, setWorkers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState('');
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        try {
            const { data } = await api.get('workers/', { params: { farm: farmId } });
            setWorkers(asList(data));
            setError('');
        } catch (err) {
            setError(getErrorMessage(err, "Ishchilarni yuklab bo'lmadi"));
        } finally {
            setLoading(false);
        }
    }, [farmId]);

    useEffect(() => {
        load();
    }, [load]);

    const handleChange = (e) => {
        const { name, type, value, checked } = e.target;
        setFormData({ ...formData, [name]: type === 'checkbox' ? checked : value });
    };

    const handleAdd = async (e) => {
        e.preventDefault();
        setSaving(true);
        setFormError('');
        try {
            const { data } = await api.post('workers/', { ...formData, farm: farmId });
            setWorkers((prev) => [data, ...prev]);
            setFormData(EMPTY_FORM);
            setShowForm(false);
        } catch (err) {
            setFormError(getErrorMessage(err, "Ishchini qo'shib bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const handleToggleFinance = async (worker) => {
        try {
            const { data } = await api.patch(`workers/${worker.id}/`, {
                can_view_finance: !worker.can_view_finance,
            });
            setWorkers((prev) => prev.map((w) => (w.id === data.id ? data : w)));
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleRemove = async (worker) => {
        const ok = window.confirm(
            `${worker.user_full_name} (@${worker.user_username}) ni fermadan olib tashlaysizmi?\n\n` +
            "Agar u boshqa hech qaysi fermada ishlamasa, uning akkaunti bloklanadi."
        );
        if (!ok) return;
        try {
            await api.delete(`workers/${worker.id}/`);
            setWorkers((prev) => prev.filter((w) => w.id !== worker.id));
        } catch (err) {
            window.alert(getErrorMessage(err, "Ishchini olib tashlab bo'lmadi"));
        }
    };

    return (
        <div className="workers-panel">
            <div className="workers-head">
                <h4>Ishchilar</h4>
                {!showForm && (
                    <button type="button" className="btn-ghost" onClick={() => setShowForm(true)}>
                        + Ishchi qo'shish
                    </button>
                )}
            </div>

            {showForm && (
                <form className="worker-form" onSubmit={handleAdd}>
                    <div className="worker-form-grid">
                        <div className="form-field">
                            <label>Ism</label>
                            <input type="text" name="first_name" value={formData.first_name} onChange={handleChange} required />
                        </div>
                        <div className="form-field">
                            <label>Familiya</label>
                            <input type="text" name="last_name" value={formData.last_name} onChange={handleChange} />
                        </div>
                        <div className="form-field">
                            <label>Username (kirish uchun)</label>
                            <input type="text" name="username" value={formData.username} onChange={handleChange}
                                autoComplete="off" required />
                        </div>
                        <div className="form-field">
                            <label>Parol</label>
                            <input type="text" name="password" value={formData.password} onChange={handleChange}
                                autoComplete="off" minLength={8} required />
                        </div>
                        <div className="form-field">
                            <label>Telefon raqam</label>
                            <input type="tel" name="phone_number" value={formData.phone_number} onChange={handleChange}
                                placeholder="+998 90 123 45 67" />
                        </div>
                    </div>
                    <label className="check-field">
                        <input type="checkbox" name="can_view_finance" checked={formData.can_view_finance}
                            onChange={handleChange} />
                        Kirim-chiqimni ko'ra olsin
                    </label>
                    <p className="workers-hint">
                        Username va parolni ishchiga o'zingiz bering, u shular bilan tizimga kiradi.
                    </p>
                    {formError && <p className="error-text">{formError}</p>}
                    <div className="farm-edit-actions">
                        <button type="submit" className="btn-primary" disabled={saving}>
                            {saving ? 'Kuting...' : "Qo'shish"}
                        </button>
                        <button type="button" className="btn-ghost" disabled={saving}
                            onClick={() => { setShowForm(false); setFormError(''); setFormData(EMPTY_FORM); }}>
                            Bekor qilish
                        </button>
                    </div>
                </form>
            )}

            {loading ? (
                <p className="workers-empty">Yuklanmoqda...</p>
            ) : error ? (
                <p className="error-text">{error}</p>
            ) : workers.length === 0 ? (
                <p className="workers-empty">Bu fermada hozircha ishchi yo'q</p>
            ) : (
                <ul className="worker-list">
                    {workers.map((w) => (
                        <li key={w.id} className="worker-item">
                            <div className="worker-info">
                                <span className="worker-name">{w.user_full_name}</span>
                                <span className="worker-meta">
                                    @{w.user_username}{w.user_phone ? ` · ${w.user_phone}` : ''}
                                </span>
                            </div>
                            <div className="worker-actions">
                                <label className="check-field">
                                    <input type="checkbox" checked={w.can_view_finance}
                                        onChange={() => handleToggleFinance(w)} />
                                    Moliyani ko'radi
                                </label>
                                <button type="button" className="farm-item-action farm-item-action--danger"
                                    onClick={() => handleRemove(w)}>
                                    Olib tashlash
                                </button>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

export default WorkersPanel;
