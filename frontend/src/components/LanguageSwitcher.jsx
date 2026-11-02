import { LANGUAGES, useLang, t } from '../i18n';
import './LanguageSwitcher.css';

// Til almashtirgich: UZ | RU. Tanlov brauzerda saqlanadi.
export default function LanguageSwitcher() {
    const { lang, setLang } = useLang();
    return (
        <div className="lang-switch" role="group" aria-label={t('Til')}>
            {LANGUAGES.map((l) => (
                <button key={l.code} type="button" title={l.name}
                    className={`lang-opt${lang === l.code ? ' lang-opt--on' : ''}`}
                    aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>
                    {l.label}
                </button>
            ))}
        </div>
    );
}
