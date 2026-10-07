import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import { formatMoney, today } from "../utils/format";

const TYPES = { kirim: "Kirim", chiqim: "Chiqim" };

const CATEGORIES = {
    ozuqa: "Ozuqa",
    dori: "Dori-darmon",
    sotuv: "Sotuv",
    ish_haqi: "Ish haqi",
    kommunal: "Kommunal xarajat",
    boshqa: "Boshqa",
};

const EMPTY_FORM = {
    transaction_type: "chiqim",
    category: "ozuqa",
    amount: "",
    date: today(),
    description: "",
};

const EMPTY_FILTERS = { transaction_type: "", category: "", date_from: "", date_to: "" };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

function Finance() {
    const { farmId } = useParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [farmError, setFarmError] = useState("");

    const [transactions, setTransactions] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const [filters, setFilters] = useState(EMPTY_FILTERS);
    const [reloadKey, setReloadKey] = useState(0);

    const [form, setForm] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState("");
    const [saving, setSaving] = useState(false);

    // Ferma nomini olish
    useEffect(() => {
        let cancelled = false;
        api.get(`farms/${farmId}/`)
            .then(({ data }) => !cancelled && setFarm(data))
            .catch((err) => {
                if (!cancelled) {
                    setFarmError(err.response?.status === 404 ? "Ferma topilmadi" : getErrorMessage(err));
                }
            });
        return () => {
            cancelled = true;
        };
    }, [farmId]);

    // Tranzaksiyalar va jamlanmani olish (filtr o'zgarsa yoki yangi yozuv qo'shilsa)
    useEffect(() => {
        let cancelled = false;
        const params = { farm: farmId };
        Object.entries(filters).forEach(([k, v]) => {
            if (v) params[k] = v;
        });

        Promise.all([api.get("finance/", { params }), api.get("finance/summary/", { params })])
            .then(([list, sum]) => {
                if (cancelled) return;
                setTransactions(asList(list.data));
                setSummary(sum.data);
                setError("");
            })
            .catch((err) => !cancelled && setError(getErrorMessage(err, "Ma'lumotlarni yuklab bo'lmadi")))
            .finally(() => !cancelled && setLoading(false));

        return () => {
            cancelled = true;
        };
    }, [farmId, filters, reloadKey]);

    const reload = () => {
        setLoading(true);
        setReloadKey((k) => k + 1);
    };

    const handleFilter = (e) => {
        const { name, value } = e.target;
        setLoading(true);
        setFilters((prev) => ({ ...prev, [name]: value }));
    };

    const clearFilters = () => {
        setLoading(true);
        setFilters(EMPTY_FILTERS);
    };

    const handleFormChange = (e) => {
        const { name, value } = e.target;
        setForm((prev) => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError("");
        setSaving(true);
        try {
            await api.post("finance/", {
                farm: Number(farmId),
                transaction_type: form.transaction_type,
                category: form.category,
                amount: form.amount,
                date: form.date,
                description: form.description.trim(),
            });
            // tur va kategoriya saqlanadi, summa va izoh tozalanadi (ketma-ket kiritish qulay bo'lsin)
            setForm((prev) => ({ ...prev, amount: "", description: "" }));
            reload();
        } catch (err) {
            setFormError(getErrorMessage(err, "Saqlashda xatolik yuz berdi"));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (tx) => {
        const label = `${TYPES[tx.transaction_type]}: ${formatMoney(tx.amount)}`;
        if (!window.confirm(`Bu yozuv o'chirilsinmi?\n${label}`)) return;
        try {
            await api.delete(`finance/${tx.id}/`);
            reload();
        } catch (err) {
            setError(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const hasFilters = Object.values(filters).some(Boolean);

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <button className="btn-ghost" onClick={logout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">← Fermalarga qaytish</Link>

                {farmError ? (
                    <p className="error-text">{farmError}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm ? farm.name : "..."}: kirim-chiqim</h2>
                        {farm && <p className="panel-subtitle">{farm.location}</p>}

                        {/* Jamlanma */}
                        <div className="stat-grid stat-grid--3">
                            <div className="stat-card">
                                <span className="stat-value amount-in">{formatMoney(summary?.income)}</span>
                                <span className="stat-label">Jami kirim</span>
                            </div>
                            <div className="stat-card">
                                <span className="stat-value amount-out">{formatMoney(summary?.expense)}</span>
                                <span className="stat-label">Jami chiqim</span>
                            </div>
                            <div className="stat-card">
                                <span className={`stat-value ${Number(summary?.balance) < 0 ? "amount-out" : ""}`}>
                                    {formatMoney(summary?.balance)}
                                </span>
                                <span className="stat-label">Balans</span>
                            </div>
                        </div>

                        {/* Yangi yozuv */}
                        <form className="farm-form" onSubmit={handleSubmit}>
                            <h3>Yangi yozuv qo'shish</h3>
                            <div className="form-row">
                                <div className="form-field">
                                    <label htmlFor="tx-type">Turi</label>
                                    <select id="tx-type" name="transaction_type" value={form.transaction_type}
                                        onChange={handleFormChange}>
                                        {Object.entries(TYPES).map(([v, l]) => (
                                            <option key={v} value={v}>{l}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-field">
                                    <label htmlFor="tx-category">Kategoriya</label>
                                    <select id="tx-category" name="category" value={form.category}
                                        onChange={handleFormChange}>
                                        {Object.entries(CATEGORIES).map(([v, l]) => (
                                            <option key={v} value={v}>{l}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-field">
                                    <label htmlFor="tx-amount">Summa (so'm)</label>
                                    <input id="tx-amount" type="number" name="amount" min="0.01" step="0.01"
                                        inputMode="decimal" value={form.amount} onChange={handleFormChange} required />
                                </div>
                                <div className="form-field">
                                    <label htmlFor="tx-date">Sana</label>
                                    <input id="tx-date" type="date" name="date" value={form.date}
                                        onChange={handleFormChange} required />
                                </div>
                            </div>
                            <div className="form-field">
                                <label htmlFor="tx-desc">Izoh (ixtiyoriy)</label>
                                <input id="tx-desc" type="text" name="description" value={form.description}
                                    onChange={handleFormChange} />
                            </div>
                            {formError && <p className="error-text" role="alert">{formError}</p>}
                            <button type="submit" className="btn-primary" disabled={saving}>
                                {saving ? "Saqlanmoqda..." : "Saqlash"}
                            </button>
                        </form>

                        {/* Filtrlar */}
                        <h3 className="section-title">Yozuvlar</h3>
                        <div className="filter-bar">
                            <select name="transaction_type" value={filters.transaction_type}
                                onChange={handleFilter} aria-label="Turi bo'yicha filtr">
                                <option value="">Barcha turlar</option>
                                {Object.entries(TYPES).map(([v, l]) => (
                                    <option key={v} value={v}>{l}</option>
                                ))}
                            </select>
                            <select name="category" value={filters.category}
                                onChange={handleFilter} aria-label="Kategoriya bo'yicha filtr">
                                <option value="">Barcha kategoriyalar</option>
                                {Object.entries(CATEGORIES).map(([v, l]) => (
                                    <option key={v} value={v}>{l}</option>
                                ))}
                            </select>
                            <input type="date" name="date_from" value={filters.date_from}
                                onChange={handleFilter} aria-label="Boshlanish sanasi" />
                            <input type="date" name="date_to" value={filters.date_to}
                                onChange={handleFilter} aria-label="Tugash sanasi" />
                            {hasFilters && (
                                <button type="button" className="btn-ghost" onClick={clearFilters}>Tozalash</button>
                            )}
                        </div>

                        {/* Ro'yxat */}
                        {loading ? (
                            <p className="empty-state">Yuklanmoqda...</p>
                        ) : error ? (
                            <div className="empty-state">
                                <p className="error-text">{error}</p>
                                <button className="btn-ghost" onClick={reload}>Qayta urinish</button>
                            </div>
                        ) : transactions.length === 0 ? (
                            <p className="empty-state">
                                {hasFilters ? "Hech narsa topilmadi" : "Hali yozuvlar yo'q"}
                            </p>
                        ) : (
                            <ul className="tx-list">
                                {transactions.map((tx) => (
                                    <li key={tx.id} className={`tx-item tx-item--${tx.transaction_type}`}>
                                        <div className="tx-main">
                                            <span className="tx-category">{CATEGORIES[tx.category] || tx.category}</span>
                                            <span className="tx-meta">
                                                {tx.date}
                                                {tx.description ? ` · ${tx.description}` : ""}
                                            </span>
                                        </div>
                                        <div className="tx-side">
                                            <span className={`tx-amount ${tx.transaction_type === "kirim" ? "amount-in" : "amount-out"}`}>
                                                {tx.transaction_type === "kirim" ? "+" : "−"}{formatMoney(tx.amount)}
                                            </span>
                                            <button type="button" className="tx-delete" onClick={() => handleDelete(tx)}
                                                aria-label="Yozuvni o'chirish">
                                                O'chirish
                                            </button>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

export default Finance;
