import { useEffect, useRef, useState } from 'react';
import useInstall from '../hooks/useInstall';
import { promptInstall } from '../offline/install';
import './InstallButton.css';

function DownloadIcon() {
    return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 20h16" />
        </svg>
    );
}

// Brauzer bir bosishda o'rnatishni bermasa, foydalanuvchiga o'z telefoniga mos qadamlarni ko'rsatamiz
function InstallGuide({ onClose }) {
    const ref = useRef(null);
    const { ios, inApp, secure } = useInstall();

    useEffect(() => {
        const dialog = ref.current;
        if (dialog && !dialog.open) dialog.showModal();
    }, []);

    let steps;
    if (!secure) {
        steps = ["Bu sahifa xavfsiz (HTTPS) emas, shuning uchun brauzer o'rnatishga ruxsat bermaydi. Ilova HTTPS manzilda ochilishi kerak."];
    } else if (inApp) {
        steps = [
            "Siz sahifani Telegram yoki boshqa ilova ichida ochgansiz, bu yerda o'rnatib bo'lmaydi.",
            "Yuqori burchakdagi ⋮ (uch nuqta) tugmasini bosing.",
            "«Brauzerda ochish» ni tanlang (Chrome yoki Safari).",
            "U yerda «Ilovani yuklab olish» tugmasini qayta bosing.",
        ];
    } else if (ios) {
        steps = [
            "Sahifani Safari brauzerida oching.",
            "Pastdagi «Ulashish» tugmasini bosing (kvadrat va yuqoriga strelka).",
            "Pastga suring va «Bosh ekranga qo'shish» ni tanlang.",
            "«Qo'shish» ni bosing. FarmLine ikonkasi bosh ekranda paydo bo'ladi.",
        ];
    } else {
        steps = [
            "Chrome brauzerida yuqori burchakdagi ⋮ (uch nuqta) tugmasini bosing.",
            "«Ilovani o'rnatish» yoki «Bosh ekranga qo'shish» ni tanlang.",
            "«O'rnatish» ni tasdiqlang. FarmLine ikonkasi bosh ekranda paydo bo'ladi.",
        ];
    }

    return (
        <dialog
            ref={ref}
            className="install-guide"
            onClose={onClose}
            onClick={(e) => { if (e.target === ref.current) ref.current.close(); }}
            aria-labelledby="install-guide-title"
        >
            <h3 id="install-guide-title">Ilovani telefonga o'rnatish</h3>
            <ol>
                {steps.map((s) => <li key={s}>{s}</li>)}
            </ol>
            <button type="button" className="btn-primary btn-auto" onClick={() => ref.current.close()}>
                Tushunarli
            </button>
        </dialog>
    );
}

// "Ilovani yuklab olish" tugmasi. O'rnatilgan bo'lsa, ko'rinmaydi.
// Sarlavhada kichik tugma (btn-install). Boshqa joyda className va yozuvni o'zingiz berasiz.
function InstallButton({ className = 'btn-install', children = 'Yuklab olish' }) {
    const { canPrompt, installed } = useInstall();
    const [guideOpen, setGuideOpen] = useState(false);

    if (installed) return null;

    const handleClick = async () => {
        if (canPrompt) {
            const outcome = await promptInstall();
            if (outcome === 'unavailable') setGuideOpen(true);
            return;
        }
        setGuideOpen(true);
    };

    return (
        <>
            <button type="button" className={className} onClick={handleClick}>
                <DownloadIcon />
                {children}
            </button>
            {guideOpen && <InstallGuide onClose={() => setGuideOpen(false)} />}
        </>
    );
}

export default InstallButton;
