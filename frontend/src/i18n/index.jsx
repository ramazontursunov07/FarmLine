import { createContext, Fragment, useContext, useEffect, useState } from 'react';
import ru from './ru';

/**
 * Ko'p tillilik (o'zbek / rus), tashqi kutubxonasiz.
 *
 * Ishlatilishi: t("O'zbekcha matn") -- o'zbekcha matnning o'zi kalit. Rus tilida tarjima ./ru/*.js fayllarida turadi;
 * tarjima topilmasa, o'zbekcha matn ko'rinadi (yangi matn qo'shilsa ilova buzilmaydi).
 * O'zgaruvchilar: t("Salom, {name}!", { name }).
 * Komponentdan tashqarida (fayl tepasidagi o'zgarmaslarda) t() ni chaqirmang: til almashganda yangilanmaydi,
 * kalitni saqlab, ko'rsatayotgan joyda t(KALIT) deb yozing.
 */
const STORAGE_KEY = 'lang';
export const LANGUAGES = [
    { code: 'uz', label: 'UZ', name: "O'zbekcha" },
    { code: 'ru', label: 'RU', name: 'Русский' },
];
const CODES = LANGUAGES.map((l) => l.code);

function readSaved() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (CODES.includes(saved)) return saved;
    } catch {
        /* localStorage yopiq bo'lishi mumkin: o'zbekcha qoladi */
    }
    return 'uz';
}

let current = readSaved();
if (typeof document !== 'undefined') document.documentElement.lang = current;

export const getLang = () => current;

export function t(text, vars) {
    if (typeof text !== 'string') return text;
    let out = current === 'ru' && Object.prototype.hasOwnProperty.call(ru, text) ? ru[text] : text;
    if (vars) out = out.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? String(vars[key]) : match));
    return out;
}

/**
 * Server yozgan qisqa faoliyat matnlari ("Ombor, kirim: 50 tonna Kepak", "Vazifa bajarildi: ...")
 * ni ruschaga o'giradi. Foydalanuvchi o'zi kiritgan nom va sarlavhalar o'zgarishsiz qoladi.
 */
export function tServer(text) {
    if (typeof text !== 'string' || current !== 'ru') return text;
    const direct = t(text);
    if (direct !== text) return direct;
    let m = text.match(/^Ombor, (kirim|sarf): (\S+) (\S+) ([\s\S]*)$/);
    if (m) return `${t('Ombor')}, ${t(m[1])}: ${m[2]} ${t(m[3])} ${m[4]}`;
    m = text.match(/^([^:\n]{2,40}): ([\s\S]*)$/);
    if (m) {
        const title = m[2].replace(/(\S+) (o'ldi|kasallandi|davolanyapti)$/, (_, a, w) => `${a} ${t(w)}`);
        return `${t(m[1])}: ${title}`;
    }
    m = text.match(/^([^:]+): (-?[\d.,]+)(°|\s\S+)\. ([\s\S]*)$/);
    if (m) return `${t(m[1])}: ${m[2]}${m[3] === '°' ? '°' : ' ' + t(m[3].trim())}. ${t(m[4])}`;
    return text;
}

/** Sana/raqam formatlari uchun brauzer tili kodi */
export const intlLocale = () => (current === 'ru' ? 'ru-RU' : 'uz-UZ');

const LangContext = createContext({ lang: 'uz', setLang: () => {} });
export const useLang = () => useContext(LangContext);

export function LanguageProvider({ children }) {
    const [lang, setLangState] = useState(current);

    const setLang = (code) => {
        if (!CODES.includes(code) || code === current) return;
        current = code;
        try {
            localStorage.setItem(STORAGE_KEY, code);
        } catch {
            /* saqlanmasa ham, shu sessiyada ishlaydi */
        }
        setLangState(code);
    };

    useEffect(() => {
        document.documentElement.lang = lang;
    }, [lang]);

    // key={lang}: til almashganda butun daraxt qayta chiziladi, shuning uchun hamma t() yangi tilda chiqadi
    return (
        <LangContext.Provider value={{ lang, setLang }}>
            <Fragment key={lang}>{children}</Fragment>
        </LangContext.Provider>
    );
}
