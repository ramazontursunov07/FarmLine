import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';
import './MilkEntry.css';

const SESSIONS = { ertalab: 'Ertalab', kechqurun: 'Kechqurun', kun: 'Butun kun' };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);
const num = (n) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function monthsOld(iso) {
    if (!iso) return null;
    const born = new Date(iso);
    const now = new Date();
    let months = (now.getFullYear() - born.getFullYear()) * 12 + now.getMonth() - born.getMonth();
    if (now.getDate() < born.getDate()) months -= 1;
    return months;
}

// Tushgacha ertalabki, undan keyin kechqurungi sog'ish deb taxmin qilamiz (o'zgartirish mumkin)
const defaultSession = () => (new Date().getHours() < 13 ? 'ertalab' : 'kechqurun');

// "8,5" va "8.5" ikkalasi ham to'g'ri. Server bitta o'nlik xonagacha qabul qiladi.
function parseLiters(raw) {
    const text = String(raw ?? '').trim().replace(',', '.');
    if (!/^\d+(\.\d)?$/.test(text)) return null;
    const value = Number(text);
    return value > 0 && value <= 100 ? value : null;
}

// Tanlangan vaqt uchun bu sigirga yozib bo'lmaydimi (allaqachon yozilgan yoki bir kunda aralashib ketadi)?
function lockText(records = [], session) {
    const same = records.find((r) => r.session === session);
    if (same) return `${SESSIONS[session]}: ${num(same.liters)} l yozilgan`;
    if (session === 'kun' && records.length) {
        const total = records.reduce((s, r) => s + Number(r.liters), 0);
        return `Ertalab/kechqurun yozilgan, jami ${num(total)} l`;
    }
    const whole = records.find((r) => r.session === 'kun');
    if (session !== 'kun' && whole) return `Butun kun yozilgan: ${num(whole.liters)} l`;
    return null;
}

// Hamma sigirning sutini birdaniga yozish: sana va vaqtni (ertalab / kechqurun / butun kun) bir marta tanlaysiz,
// keyin har bir sigir uchun litrni kiritasiz. Har biri o'sha sigirning kartochkasiga yoziladi.
function MilkEntry({ farmId, animals, onSaved }) {
    const [open, setOpen] = useState(false);
    const [date, setDate] = useState(today());
    const [session, setSession] = useState(defaultSession);
    const [existing, setExisting] = useState({});
    const [values, setValues] = useState({});
    const [errors, setErrors] = useState({});
    const [notice, setNotice] = useState('');
    const [formError, setFormError] = useState('');
    const [loadError, setLoadError] = useState('');
    const [saving, setSaving] = useState(false);
    const formRef = useRef(null);

    const loadExisting = useCallback(async () => {
        try {
            const res = await api.get('animals-milk/', { params: { farm: farmId, date_from: date, date_to: date } });
            const map = {};
            for (const r of asList(res.data)) {
                (map[r.animal] = map[r.animal] || []).push({ session: r.session, liters: r.liters });
            }
            setExisting(map);
            setLoadError('');
        } catch {
            setLoadError("Shu kungi yozuvlar yuklanmadi. Yozish mumkin, lekin allaqachon yozilgan bo'lsa, server rad etadi.");
        }
    }, [farmId, date]);

    useEffect(() => {
        if (open) loadExisting();
    }, [open, loadExisting]);

    // Sut beradigan yoshdagi faol urg'ochilar (1 yoshgacha bo'lganlar, agar o'sha kuni yozuvi bo'lmasa, chiqmaydi)
    const cows = useMemo(
        () => animals
            .filter((a) => a.sex === 'urgochi' && a.status === 'faol')
            .filter((a) => {
                const age = monthsOld(a.birth_date);
                return age == null || age >= 12 || (existing[a.id]?.length ?? 0) > 0;
            })
            .sort((a, b) => String(a.tag_number).localeCompare(String(b.tag_number), undefined, { numeric: true })),
        [animals, existing]
    );

    if (cows.length === 0) return null;

    const rows = cows.map((a) => ({ animal: a, lock: lockText(existing[a.id], session) }));
    const typed = rows.filter((r) => !r.lock && String(values[r.animal.id] ?? '').trim() !== '');
    const total = typed.reduce((s, r) => s + (parseLiters(values[r.animal.id]) || 0), 0);

    const setValue = (id, value) => {
        setValues({ ...values, [id]: value });
        if (errors[id]) setErrors({ ...errors, [id]: '' });
    };

    // Enter bosilsa, keyingi sigirga o'tadi (telefonda "Keyingi" tugmasi); oxirgisida saqlaydi
    const handleKeyDown = (e) => {
        if (e.key !== 'Enter') return;
        const inputs = [...formRef.current.querySelectorAll('input[data-milk]:not(:disabled)')];
        const next = inputs[inputs.indexOf(e.target) + 1];
        if (next) {
            e.preventDefault();
            next.focus();
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError('');
        setNotice('');

        const invalid = {};
        for (const r of typed) {
            if (parseLiters(values[r.animal.id]) == null) {
                invalid[r.animal.id] = "Litrni to'g'ri kiriting (masalan 8 yoki 8,5; 100 dan oshmasin)";
            }
        }
        if (Object.keys(invalid).length) {
            setErrors(invalid);
            setFormError("Ba'zi sigirlarning litri noto'g'ri kiritilgan.");
            return;
        }
        if (typed.length === 0) {
            setFormError("Kamida bitta sigirning litrini kiriting.");
            return;
        }

        setSaving(true);
        const results = await Promise.allSettled(
            typed.map((r) => api.post('animals-milk/', {
                animal: r.animal.id, date, session, liters: parseLiters(values[r.animal.id]),
            }))
        );

        const nextValues = { ...values };
        const nextErrors = {};
        const nextExisting = { ...existing };
        let saved = 0;
        let savedLiters = 0;
        let pending = false;
        results.forEach((res, i) => {
            const { animal } = typed[i];
            if (res.status === 'fulfilled') {
                saved += 1;
                savedLiters += parseLiters(values[animal.id]);
                pending = pending || Boolean(res.value?.data?._pending);
                delete nextValues[animal.id];
                nextExisting[animal.id] = [...(nextExisting[animal.id] || []), { session, liters: parseLiters(values[animal.id]) }];
            } else {
                nextErrors[animal.id] = getErrorMessage(res.reason, "Yozib bo'lmadi");
            }
        });
        setValues(nextValues);
        setErrors(nextErrors);
        setExisting(nextExisting);
        setSaving(false);

        if (saved > 0) {
            setNotice(
                `${saved} ta sigirning ${SESSIONS[session].toLowerCase()} suti yozildi: jami ${num(savedLiters)} l.` +
                (pending ? " Internet yo'q: ulanganda serverga yuboriladi." : '')
            );
            onSaved?.();
        }
        if (Object.keys(nextErrors).length) {
            setFormError(`${Object.keys(nextErrors).length} ta sigirning sutini yozib bo'lmadi. Pastdagi xabarlarni ko'ring.`);
        }
    };

    return (
        <section className="milk-entry">
            <button type="button" className={open ? 'btn-ghost' : 'btn-primary btn-auto'} onClick={() => setOpen(!open)}
                aria-expanded={open}>
                {open ? 'Sut yozishni yopish' : 'Sut yozish'}
            </button>

            {open && (
                <div className="work-card milk-entry-card">
                    <form ref={formRef} onSubmit={handleSubmit} onKeyDown={handleKeyDown} noValidate>
                        <div className="form-row">
                            <div className="form-field">
                                <label htmlFor="milk-date">Sana</label>
                                <input id="milk-date" type="date" value={date} max={today()} required
                                    onChange={(e) => { setDate(e.target.value || today()); setNotice(''); }} />
                            </div>
                            <div className="form-field">
                                <span className="milk-entry-label" id="milk-session-label">Qaysi vaqtdagi sut</span>
                                <div className="milk-entry-seg" role="group" aria-labelledby="milk-session-label">
                                    {Object.entries(SESSIONS).map(([value, label]) => (
                                        <button key={value} type="button" aria-pressed={session === value}
                                            className={session === value ? 'is-active' : ''}
                                            onClick={() => { setSession(value); setNotice(''); }}>
                                            {label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <p className="workers-hint">
                            {session === 'kun'
                                ? "«Butun kun» tanlansa, shu kunga ertalab/kechqurun alohida yozilmaydi: sutni kun bo'yicha jami kiriting."
                                : "Sog'ilmagan sigirlarning litrini bo'sh qoldiring. Yozilgan sutni o'zgartirish uchun sigir kartochkasini oching."}
                        </p>

                        {loadError && <p className="error-text" role="status">{loadError}</p>}

                        <ul className="milk-entry-list">
                            {rows.map(({ animal, lock }) => (
                                <li key={animal.id} className={`milk-entry-row${lock ? ' is-done' : ''}`}>
                                    <label htmlFor={`milk-${animal.id}`} className="milk-entry-name">
                                        №{animal.tag_number}{animal.name ? ` · ${animal.name}` : ''}
                                    </label>
                                    {lock ? (
                                        <span className="milk-entry-done">✓ {lock}</span>
                                    ) : (
                                        <span className="milk-entry-field">
                                            <input id={`milk-${animal.id}`} data-milk inputMode="decimal" enterKeyHint="next"
                                                placeholder="0" autoComplete="off" value={values[animal.id] ?? ''}
                                                aria-label={`№${animal.tag_number} ${SESSIONS[session].toLowerCase()} suti, litr`}
                                                aria-invalid={Boolean(errors[animal.id])}
                                                onChange={(e) => setValue(animal.id, e.target.value)} />
                                            <span className="milk-entry-unit">l</span>
                                        </span>
                                    )}
                                    {errors[animal.id] && (
                                        <span className="milk-entry-error error-text" role="alert">{errors[animal.id]}</span>
                                    )}
                                </li>
                            ))}
                        </ul>

                        {formError && <p className="error-text" role="alert">{formError}</p>}
                        {notice && <p className="milk-entry-notice" role="status">{notice}</p>}

                        <div className="milk-entry-actions">
                            <button type="submit" className="btn-primary btn-auto" disabled={saving || typed.length === 0}>
                                {saving ? 'Saqlanmoqda...' : `Saqlash: ${SESSIONS[session].toLowerCase()}`}
                            </button>
                            <span className="milk-entry-total">
                                {typed.length > 0 ? `${typed.length} ta sigir, jami ${num(total)} l` : 'Litr kiritilmagan'}
                            </span>
                        </div>
                    </form>
                </div>
            )}
        </section>
    );
}

export default MilkEntry;
