import { useCallback, useEffect, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

const POLL_MS = 3000;
const MAX_POLLS = 100; // ~5 daqiqa, keyin kutishni to'xtatamiz

// Telegram ulanmagan foydalanuvchiga ko'rinadigan taklif. Ulangan bo'lsa umuman chiqmaydi.
function TelegramBanner() {
    const [linked, setLinked] = useState(null); // null: hali bilinmaydi (banner ko'rsatilmaydi)
    const [link, setLink] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [justLinked, setJustLinked] = useState(false);
    const [polls, setPolls] = useState(0);

    const check = useCallback(async () => {
        try {
            const { data } = await api.get('users/profile/');
            setLinked(Boolean(data.telegram_linked));
            return Boolean(data.telegram_linked);
        } catch {
            return null; // tekshirib bo'lmasa, bannerni ko'rsatmaymiz: asosiy sahifa halaqit olmasin
        }
    }, []);

    useEffect(() => {
        check();
    }, [check]);

    // Havola ochilgach, ulanishni o'zi aniqlaymiz
    useEffect(() => {
        if (!link || linked || polls >= MAX_POLLS) return undefined;
        const timer = setTimeout(async () => {
            const ok = await check();
            if (ok) setJustLinked(true);
            setPolls((p) => p + 1);
        }, POLL_MS);
        return () => clearTimeout(timer);
    }, [link, linked, polls, check]);

    // "Ulandi" xabarini bir ozdan keyin yashiramiz
    useEffect(() => {
        if (!justLinked) return undefined;
        const timer = setTimeout(() => setJustLinked(false), 5000);
        return () => clearTimeout(timer);
    }, [justLinked]);

    const handleLink = async () => {
        setError('');
        setBusy(true);
        // Oynani javobdan oldin ochamiz, aks holda brauzer uni reklama oynasi deb to'sib qo'yadi
        const win = window.open('', '_blank');
        if (win) win.opener = null;
        try {
            const { data } = await api.post('users/telegram/link/');
            setLink(data.telegram_link);
            setPolls(0);
            if (win) win.location.href = data.telegram_link;
        } catch (err) {
            if (win) win.close();
            setError(getErrorMessage(err, "Havola yaratib bo'lmadi"));
        } finally {
            setBusy(false);
        }
    };

    if (justLinked) {
        return (
            <div className="tg-banner tg-banner--done" role="status">
                <strong>Telegram ulandi ✓</strong>
                <span>Endi parolni tiklash havolalari va ogohlantirishlar shu yerga keladi.</span>
            </div>
        );
    }
    if (linked !== false) return null;

    return (
        <div className="tg-banner" role="region" aria-label="Telegramni ulash">
            <svg className="tg-banner-icon" viewBox="0 0 24 24" width="28" height="28" fill="none"
                stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 4L3 11l6 2 2 6 3-4 5 3L21 4zM9 13l12-9" />
            </svg>

            <div className="tg-banner-text">
                <strong>Telegramni ulang</strong>
                {link ? (
                    <span>
                        Telegramda botni ochib «Start» tugmasini bosing. Ulanish avtomatik aniqlanadi.{' '}
                        <a href={link} target="_blank" rel="noreferrer">Telegram ochilmadimi? Bu yerni bosing</a>
                    </span>
                ) : (
                    <span>
                        Parolni unutsangiz, tiklash havolasi faqat Telegramga yuboriladi. Ombor, vazifa va
                        kirim-chiqim haqidagi ogohlantirishlar ham shu yerga keladi.
                    </span>
                )}
                {error && <span className="tg-banner-error" role="alert">{error}</span>}
            </div>

            <button type="button" className="tg-banner-button" onClick={handleLink} disabled={busy}>
                {busy ? 'Kuting...' : link ? 'Qayta ochish' : 'Telegramga ulash'}
            </button>
        </div>
    );
}

export default TelegramBanner;
