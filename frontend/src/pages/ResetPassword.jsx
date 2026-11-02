import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { t } from '../i18n';

function ResetPassword() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token');

    const [newPassword, setNewPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [showPasswords, setShowPasswords] = useState(false);
    const [error, setError] = useState('');
    const [done, setDone] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (newPassword !== confirm) {
            setError(t('Parollar bir xil emas'));
            return;
        }

        setLoading(true);
        try {
            await api.post('users/reset-password/', { token, new_password: newPassword });
            setDone(true);
        } catch (err) {
            setError(getErrorMessage(err, t("Parolni yangilab bo'lmadi")));
        } finally {
            setLoading(false);
        }
    };

    if (!token) {
        return (
            <div className="auth-page">
                <div className="lang-corner"><LanguageSwitcher /></div>
                <div className="auth-card">
                    <h2>{t('Parolni tiklash')}</h2>
                    <p className="error-text" role="alert">{t("Havola noto'g'ri: token topilmadi.")}</p>
                    <p className="auth-footer">
                        <Link to="/forgot-password">{t("Yangi havola so'rash")}</Link>
                    </p>
                </div>
            </div>
        );
    }

    if (done) {
        return (
            <div className="auth-page">
                <div className="lang-corner"><LanguageSwitcher /></div>
                <div className="auth-card">
                    <h2>{t('Parol yangilandi')}</h2>
                    <p className="success-text" role="status">{t('Endi yangi parol bilan kirishingiz mumkin.')}</p>
                    <p className="auth-footer">
                        <Link to="/login">{t('Kirish')}</Link>
                    </p>
                </div>
            </div>
        );
    }

    const inputType = showPasswords ? 'text' : 'password';

    return (
        <div className="auth-page">
            <div className="lang-corner"><LanguageSwitcher /></div>
            <div className="auth-card">
                <h2>{t('Yangi parol')}</h2>
                <form onSubmit={handleSubmit}>
                    <div className="form-field">
                        <label>{t('Yangi parol')}</label>
                        <input type={inputType} value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            autoComplete="new-password" minLength={8} required />
                    </div>
                    <div className="form-field">
                        <label>{t('Yangi parolni takrorlang')}</label>
                        <input type={inputType} value={confirm}
                            onChange={(e) => setConfirm(e.target.value)}
                            autoComplete="new-password" minLength={8} required />
                    </div>
                    <label className="check-field">
                        <input type="checkbox" checked={showPasswords}
                            onChange={(e) => setShowPasswords(e.target.checked)} />
                        {t("Parollarni ko'rsatish")}
                    </label>
                    <p className="workers-hint">
                        {t("Kamida 8 ta belgi bo'lsin va faqat raqamlardan iborat bo'lmasin.")}
                    </p>
                    {error && <p className="error-text" role="alert">{error}</p>}
                    <button type="submit" className="btn-primary" disabled={loading}>
                        {loading ? t('Kuting...') : t('Parolni yangilash')}
                    </button>
                </form>
                <p className="auth-footer">
                    <Link to="/login">{t('← Kirishga qaytish')}</Link>
                </p>
            </div>
        </div>
    );
}

export default ResetPassword;
