import { promptInstall, useCanInstall } from '../offline/install';

// Brauzer ilovani o'rnatishga ruxsat bergandagina ko'rinadi (o'rnatilgan bo'lsa, yashiriladi)
function InstallButton() {
    const canInstall = useCanInstall();
    if (!canInstall) return null;

    return (
        <button type="button" className="btn-install" onClick={promptInstall}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3v12" />
                <path d="m7 10 5 5 5-5" />
                <path d="M5 21h14" />
            </svg>
            Ilovani o'rnatish
        </button>
    );
}

export default InstallButton;
