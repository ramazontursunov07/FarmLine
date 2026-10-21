import { useState, useEffect, useCallback } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatMoney, today } from '../utils/format';

const num = (n) => Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

function formatDate(iso) {
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

// Sut ombori va sotish: sog'ilgan - sotilgan = qolgan. Sotilganda pul moliyada "Kirim" bo'lib yoziladi.
function MilkSales({ farmId, refreshKey }) {
    const [stock, setStock] = useState(null);
    const [sales, setSales] = useState([]);
    const [error, setError] = useState('');
    const [form, setForm] = useState({ liters: '', price_per_liter: '', date: today(), note: '' });
    const [formError, setFormError] = useState('');
    const [saving, setSaving] = useState(false);
    const [version, setVersion] = useState(0);

    const load = useCallback(async () => {
        try {
            const { data } = await api.get('animals-milk-sale/stock/', { params: { farm: farmId } });
            setStock(data);
            if (data.can_sell) {
                const res = await api.get('animals-milk-sale/', { params: { farm: farmId } });
                setSales(asList(res.data).slice(0, 10));
            }
            setError('');
        } catch (err) {
            setError(getErrorMessage(err, "Sut omborini yuklab bo'lmadi"));
        }
    }, [farmId]);

    useEffect(() => {
        load();
    }, [load, refreshKey, version]);

    const handleChange = (e) => setForm({ ...form, [e.target.name]: e.target.value });

    const total = (Number(form.liters) || 0) * (Number(form.price_per_liter) || 0);

    const sell = async (confirmWithheld) => {
        setSaving(true);
        setFormError('');
        try {
            await api.post('animals-milk-sale/', {
                farm: Number(farmId),
                date: form.date,
                liters: form.liters,
                price_per_liter: form.price_per_liter,
                note: form.note.trim(),
                ...(confirmWithheld ? { confirm_withheld: true } : {}),
            });
            setForm({ ...form, liters: '', note: '' });
            setVersion((v) => v + 1);
        } catch (err) {
            const message = getErrorMessage(err, "Sutni sotib bo'lmadi (internet bormi?)");
            // Dori ushlab turish muddatidagi sut: ogohlantiramiz, fermer o'zi qaror qiladi
            if (!confirmWithheld && message.includes('ushlab turish')) {
                setSaving(false);
                if (window.confirm(`${message}\n\nAntibiotikli sut odamni kasal qilishi yoki sutni qaytarishga olib kelishi mumkin. Baribir sotasizmi?`)) {
                    await sell(true);
                } else {
                    setFormError(message);
                }
                return;
            }
            setFormError(message);
        } finally {
            setSaving(false);
        }
    };

    const handleSell = (e) => {
        e.preventDefault();
        sell(false);
    };

    // Ro'yxatdan o'chirish: faqat yozuv yo'qoladi, balans va sotilgan sut hisobi o'zgarmaydi
    const handleDelete = async (s) => {
        const ok = window.confirm(
            `${formatDate(s.date)} dagi ${num(s.liters)} l sotuv yozuvini ro'yxatdan o'chirasizmi?\n\n` +
            `Faqat yozuv o'chadi: balans (${formatMoney(s.amount)} kirim) va sotilgan sut hisobi o'zgarmaydi.`
        );
        if (!ok) return;
        try {
            await api.delete(`animals-milk-sale/${s.id}/`);
            setVersion((v) => v + 1);
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    // Xato kiritilgan sotuvni bekor qilish: sut omborga qaytadi, pul kirimdan olib tashlanadi
    const handleCancel = async (s) => {
        const ok = window.confirm(
            `${formatDate(s.date)} dagi ${num(s.liters)} l sotuv xato kiritilganmi?\n\n` +
            `Bekor qilinsa, sut omborga qaytadi, ${formatMoney(s.amount)} esa kirimdan olib tashlanadi.`
        );
        if (!ok) return;
        try {
            await api.post(`animals-milk-sale/${s.id}/cancel/`);
            setVersion((v) => v + 1);
        } catch (err) {
            window.alert(getErrorMessage(err, "Bekor qilib bo'lmadi"));
        }
    };

    if (error) return <p className="error-text" role="alert">{error}</p>;
    if (!stock) return null;

    return (
        <section className="milk-report">
            <h3 className="section-title">Sut ombori</h3>
            <div className="stat-grid stat-grid--3">
                <div className="stat-card">
                    <span className="stat-value">{num(stock.produced)} l</span>
                    <span className="stat-label">Jami sog'ilgan</span>
                </div>
                <div className="stat-card">
                    <span className="stat-value">{num(stock.sold)} l</span>
                    <span className="stat-label">Sotilgan</span>
                </div>
                <div className="stat-card">
                    <span className="stat-value">{num(stock.available)} l</span>
                    <span className="stat-label">Omborda qolgan</span>
                </div>
            </div>

            {stock.withdrawals?.length > 0 && (
                <div className="withdrawal-box" role="alert">
                    <strong>⛔ Dori ushlab turish muddati: {stock.withdrawals.length} ta sigir</strong>
                    <span>
                        Bu sigirlarning sutini va go'shtini hozircha sotmang.
                        {Number(stock.withheld) > 0 && ` Ombordagi ${num(stock.withheld)} l sut sotuvga yaroqsiz, sotsa bo'ladigani: ${num(stock.sellable)} l.`}
                    </span>
                    <ul>
                        {stock.withdrawals.map((w) => (
                            <li key={w.animal}>
                                №{w.tag_number}{w.name ? ` ${w.name}` : ''} — {w.medicine}:{' '}
                                {w.until ? `${formatDate(w.until)} gacha (${w.days_left} kun qoldi)` : 'davolash davom etmoqda'}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {stock.can_sell && (
                <div className="work-card">
                    <form className="animal-inline-form" onSubmit={handleSell}>
                        <div className="form-row">
                            <div className="form-field">
                                <label>Necha litr sotildi</label>
                                <input type="number" name="liters" min="0.1" step="0.1" max={stock.available}
                                    value={form.liters} onChange={handleChange} required />
                            </div>
                            <div className="form-field">
                                <label>1 litr narxi (so'm)</label>
                                <input type="number" name="price_per_liter" min="1" step="1"
                                    value={form.price_per_liter} onChange={handleChange} required />
                            </div>
                        </div>
                        <div className="form-row">
                            <div className="form-field">
                                <label>Sana</label>
                                <input type="date" name="date" value={form.date} max={today()}
                                    onChange={handleChange} required />
                            </div>
                            <div className="form-field">
                                <label>Kimga sotildi (ixtiyoriy)</label>
                                <input type="text" name="note" value={form.note} maxLength={200}
                                    onChange={handleChange} />
                            </div>
                        </div>
                        <p className="workers-hint">
                            {total > 0
                                ? `Jami: ${formatMoney(total)}. Sotilgach, bu pul kirim sifatida balansga qo'shiladi.`
                                : "Sotilgach, pul kirim sifatida balansga qo'shiladi va sut ombordan ayriladi."}
                        </p>
                        {formError && <p className="error-text" role="alert">{formError}</p>}
                        <button type="submit" className="btn-primary btn-auto" disabled={saving || Number(stock.available) <= 0}>
                            {saving ? 'Kuting...' : 'Sutni sotish'}
                        </button>
                    </form>

                    {sales.length > 0 && (
                        <ul className="work-list">
                            {sales.map((s) => (
                                <li key={s.id} className="work-item">
                                    <div className="work-main">
                                        <span className="work-title">{num(s.liters)} l × {formatMoney(s.price_per_liter)}</span>
                                        <span className="work-meta">
                                            {formatDate(s.date)} · jami {formatMoney(s.amount)}
                                            {s.note ? ` · ${s.note}` : ''}
                                        </span>
                                    </div>
                                    <div className="work-side">
                                        <button type="button" className="farm-item-action"
                                            onClick={() => handleDelete(s)}>
                                            O'chirish
                                        </button>
                                        <button type="button" className="farm-item-action farm-item-action--danger"
                                            onClick={() => handleCancel(s)}>
                                            Xato — bekor qilish
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </section>
    );
}

export default MilkSales;
