import LanguageSwitcher from '../components/LanguageSwitcher';
import NotificationBell from '../components/NotificationBell';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import useInstall from '../hooks/useInstall';
import InstallButton from '../components/InstallButton';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { t } from '../i18n';

const ROLES = { fermer: 'Fermer', ishchi: 'Ishchi', admin: 'Admin' };

function Profile() {
    const { installed } = useInstall();
    const { user, logout } = useAuth();

    // Telegram ulanishi
    const [telegramLinked, setTelegramLinked] = useState(null); // null: hali yuklanmagan
    const [telegramLink, setTelegramLink] = useState('');
    const [telegramBusy, setTelegramBusy] = useState(false);
    const [telegramError, setTelegramError] = useState('');

    const loadTelegramStatus = useCallback(async () => {
        try {
            const { data } = await api.get('users/profile/');
            const linked = Boolean(data.telegram_linked);
            setTelegramLinked(linked);
            setTelegramError('');
            if (linked) setTelegramLink('');
        } catch (err) {
            setTelegramError(getErrorMessage(err, t("Telegram holatini olib bo'lmadi")));
        }
    }, []);

    useEffect(() => {
        loadTelegramStatus();
    }, [loadTelegramStatus]);

    // Havola ochilgandan keyin ulanish holatini har 3 soniyada tekshiramiz
    useEffect(() => {
        if (!telegramLink || telegramLinked) return undefined;
        const timer = setInterval(loadTelegramStatus, 3000);
        return () => clearInterval(timer);
    }, [telegramLink, telegramLinked, loadTelegramStatus]);

    const handleLinkTelegram = async () => {
        setTelegramError('');
        setTelegramBusy(true);
        try {
            const { data } = await api.post('users/telegram/link/');
            setTelegramLink(data.telegram_link);
        } catch (err) {
            setTelegramError(getErrorMessage(err, t("Havola yaratib bo'lmadi")));
        } finally {
            setTelegramBusy(false);
        }
    };

    const handleUnlinkTelegram = async () => {
        if (!window.confirm(t("Telegram ulanishini o'chirasizmi? Parolni tiklash havolalari va ogohlantirishlar endi kelmaydi."))) {
            return;
        }
        setTelegramError('');
        setTelegramBusy(true);
        try {
            await api.delete('users/telegram/link/');
            setTelegramLinked(false);
            setTelegramLink('');
        } catch (err) {
            setTelegramError(getErrorMessage(err, t("Ulanishni o'chirib bo'lmadi")));
        } finally {
            setTelegramBusy(false);
        }
    };

    const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>{t('FarmLine')}</h1>
                <div className="user-bar">
                    <span>{t('Salom, {name}!', { name: user.first_name || user.username })}</span>
                    <LanguageSwitcher />
                    <NotificationBell />
                    <button className="btn-ghost" onClick={logout}>{t('Chiqish')}</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">{t('← Orqaga')}</Link>

                <h2 className="panel-title">{t('Profil')}</h2>
                <p className="panel-subtitle">{t("Shaxsiy ma'lumotlar va xavfsizlik")}</p>

                <div className="work-card profile-info">
                    <div>
                        <span className="work-meta">{t('Ism-familiya')}</span>
                        <span className="work-title">{fullName || '—'}</span>
                    </div>
                    <div>
                        <span className="work-meta">{t('Username')}</span>
                        <span className="work-title">{user.username}</span>
                    </div>
                    <div>
                        <span className="work-meta">{t('Rol')}</span>
                        <span className="work-title">{t(ROLES[user.role]) ? t(ROLES[user.role]) : user.role}</span>
                    </div>
                </div>

                <h3 className="section-title">{t('Telegram')}</h3>
                <div className="work-card">
                    {telegramLinked === null && !telegramError && (
                        <p className="workers-hint">{t('Yuklanmoqda...')}</p>
                    )}

                    {telegramLinked === null && telegramError && (
                        <button type="button" className="btn-ghost" onClick={loadTelegramStatus}>
                            {t('Qayta urinish')}
                        </button>
                    )}

                    {telegramLinked === true && (
                        <>
                            <p className="success-text">{t('Telegram ulangan ✓')}</p>
                            <p className="workers-hint">
                                {t('Parolni tiklash havolalari va ogohlantirishlar shu Telegramga yuboriladi.')}
                            </p>
                            <button type="button" className="btn-ghost" onClick={handleUnlinkTelegram}
                                disabled={telegramBusy}>
                                {t("Ulanishni o'chirish")}
                            </button>
                        </>
                    )}

                    {telegramLinked === false && (
                        <>
                            <p className="workers-hint">
                                {t("Telegram ulanmagan. Parolni tiklash havolasi va ogohlantirishlar faqat ulangan Telegramga yuboriladi, shuning uchun hozir ulab qo'ying.")}
                            </p>

                            {telegramLink ? (
                                <>
                                    <a href={telegramLink} target="_blank" rel="noreferrer"
                                        className="btn-primary btn-auto"
                                        style={{ display: 'inline-block', textAlign: 'center', textDecoration: 'none' }}>
                                        {t('Telegramda ochish')}
                                    </a>
                                    <p className="workers-hint">
                                        {t('Botda "Start" tugmasini bosing. Havola 10 daqiqa amal qiladi, ulanish avtomatik aniqlanadi.')}
                                    </p>
                                </>
                            ) : (
                                <button type="button" className="btn-primary btn-auto"
                                    onClick={handleLinkTelegram} disabled={telegramBusy}>
                                    {telegramBusy ? t('Kuting...') : t('Telegramni ulash')}
                                </button>
                            )}
                        </>
                    )}

                    {telegramError && <p className="error-text" role="alert">{telegramError}</p>}
                </div>

                <h3 className="section-title">{t('Ilova')}</h3>
                <div className="work-card">
                    {installed ? (
                        <p className="workers-hint">{t("Ilova telefoningizga o'rnatilgan ✓")}</p>
                    ) : (
                        <>
                            <p className="workers-hint">
                                {t('Ilovani telefoningizga yuklab oling: bosh ekrandan bir bosishda ochiladi va internet yomon joyda ham ishlaydi.')}
                            </p>
                            <InstallButton className="btn-primary btn-auto install-btn">{t('Ilovani yuklab olish')}</InstallButton>
                        </>
                    )}
                </div>
            </main>
        </div>
    );
}

export default Profile;
