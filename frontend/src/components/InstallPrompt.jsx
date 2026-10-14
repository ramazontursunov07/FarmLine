import { useState } from 'react';
import useInstall from '../hooks/useInstall';
import InstallButton from './InstallButton';

const DISMISS_KEY = 'pwa-install-dismissed-at';
const DISMISS_DAYS = 14;

function recentlyDismissed() {
    try {
        const at = Number(localStorage.getItem(DISMISS_KEY));
        return Boolean(at) && Date.now() - at < DISMISS_DAYS * 24 * 60 * 60 * 1000;
    } catch {
        return false;
    }
}

// Dashboard tepasidagi taklif: ilova o'rnatilmagan bo'lsa HAR DOIM ko'rinadi (brauzer qaysi usulni
// qo'llab-quvvatlashidan qat'i nazar), "Keyinroq" bosilsa 14 kunga yashiriladi.
// O'rnatish tugmasi Profil va Kirish sahifasida doim turadi.
function InstallPrompt() {
    const { installed } = useInstall();
    const [hidden, setHidden] = useState(recentlyDismissed);

    if (installed || hidden) return null;

    const dismiss = () => {
        try {
            localStorage.setItem(DISMISS_KEY, String(Date.now()));
        } catch {
            // xotira yopiq bo'lsa ham banner shu sessiyada yopiladi
        }
        setHidden(true);
    };

    return (
        <div className="install-banner" role="region" aria-label="Ilovani yuklab olish">
            <div className="install-banner-text">
                <strong>Ilovani telefoningizga yuklab oling</strong>
                <span>Bosh ekrandan bir bosishda ochiladi va internet yomon joyda ham ishlaydi.</span>
            </div>
            <InstallButton className="install-banner-button install-btn" />
            <button type="button" className="install-banner-close" onClick={dismiss}>
                Keyinroq
            </button>
        </div>
    );
}

export default InstallPrompt;
