import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const ROLES = { fermer: 'Fermer', ishchi: 'Ishchi', admin: 'Admin' };
const EMPTY = { old_password: '', new_password: '', confirm: '' };

function Profile() {
    const { user, logout } = useAuth();

    const [form, setForm] = useState(EMPTY);
    const [showPasswords, setShowPasswords] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [saving, setSaving] = useState(false);

    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
        setSuccess('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        if (form.new_password !== form.confirm) {
            setError('Yangi parollar bir xil emas');
            return;
        }

        setSaving(true);
        try {
            await api.put('users/change-password/', {
                old_password: form.old_password,
                new_password: form.new_password,
            });
            setForm(EMPTY);
            setSuccess("Parol muvaffaqiyatli o'zgartirildi");
        } catch (err) {
            setError(getErrorMessage(err, "Parolni o'zgartirib bo'lmadi"));
        } finally {
            setSaving(false);
        }
    };

    const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
    const inputType = showPasswords ? 'text' : 'password';

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <button className="btn-ghost" onClick={logout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">← Orqaga</Link>

                <h2 className="panel-title">Profil</h2>
                <p className="panel-subtitle">Shaxsiy ma'lumotlar va xavfsizlik</p>

                <div className="work-card profile-info">
                    <div>
                        <span className="work-meta">Ism-familiya</span>
                        <span className="work-title">{fullName || '—'}</span>
                    </div>
                    <div>
                        <span className="work-meta">Username</span>
                        <span className="work-title">{user.username}</span>
                    </div>
                    <div>
                        <span className="work-meta">Rol</span>
                        <span className="work-title">{ROLES[user.role] || user.role}</span>
                    </div>
                </div>

                <h3 className="section-title">Parolni o'zgartirish</h3>
                <div className="work-card">
                    <form onSubmit={handleSubmit}>
                        <div className="form-field">
                            <label>Hozirgi parol</label>
                            <input type={inputType} name="old_password" value={form.old_password}
                                onChange={handleChange} autoComplete="current-password" required />
                        </div>
                        <div className="form-field">
                            <label>Yangi parol</label>
                            <input type={inputType} name="new_password" value={form.new_password}
                                onChange={handleChange} autoComplete="new-password" minLength={8} required />
                        </div>
                        <div className="form-field">
                            <label>Yangi parolni takrorlang</label>
                            <input type={inputType} name="confirm" value={form.confirm}
                                onChange={handleChange} autoComplete="new-password" minLength={8} required />
                        </div>

                        <label className="check-field">
                            <input type="checkbox" checked={showPasswords}
                                onChange={(e) => setShowPasswords(e.target.checked)} />
                            Parollarni ko'rsatish
                        </label>
                        <p className="workers-hint">
                            Kamida 8 ta belgi bo'lsin, faqat raqamlardan iborat bo'lmasin va username'ga o'xshamasin.
                        </p>

                        {error && <p className="error-text" role="alert">{error}</p>}
                        {success && <p className="success-text" role="status">{success}</p>}

                        <button type="submit" className="btn-primary btn-auto" disabled={saving}>
                            {saving ? 'Kuting...' : "Parolni o'zgartirish"}
                        </button>
                    </form>
                </div>
            </main>
        </div>
    );
}

export default Profile;
