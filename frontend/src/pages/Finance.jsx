import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import api from "../api/axios";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../utils/errors";
import { formatMoney, formatPeriod, today } from "../utils/format";
import InstallButton from '../components/InstallButton';
import LanguageSwitcher from '../components/LanguageSwitcher';
import NotificationBell from '../components/NotificationBell';
import ReportDownload from '../components/ReportDownload';
import CreditFields from '../components/CreditFields';
import { EMPTY_CREDIT, creditPayload } from '../utils/credit';
import { t } from '../i18n';

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
    animal_group: "",
    animal_count: "",
};

const EMPTY_FILTERS = { transaction_type: "", category: "", date_from: "", date_to: "" };

// Telefonda "so'm" yozuvi yashiriladi (jadval ekranga sig'sin); kompyuterda to'liq ko'rinadi
function Money({ value }) {
    const text = formatMoney(value);
    const unit = t("so'm");
    if (!text.endsWith(` ${unit}`)) return <>{text}</>;
    return <>{text.slice(0, -(unit.length + 1))}<span className="hide-sm"> {unit}</span></>;
}

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

    const [reportPeriod, setReportPeriod] = useState("month");
    const [report, setReport] = useState([]);
    const [reportError, setReportError] = useState("");

    const [groups, setGroups] = useState([]);

    const [form, setForm] = useState(EMPTY_FORM);
    const [formError, setFormError] = useState("");
    const [formNotice, setFormNotice] = useState("");
    const [credit, setCredit] = useState(EMPTY_CREDIT);
    const [saving, setSaving] = useState(false);

    // Ferma nomini olish
    useEffect(() => {
        let cancelled = false;
        api.get(`farms/${farmId}/`)
            .then(({ data }) => !cancelled && setFarm(data))
            .catch((err) => {
                if (!cancelled) {
                    setFarmError(err.response?.status === 404 ? t("Ferma topilmadi") : getErrorMessage(err));
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
            .catch((err) => !cancelled && setError(getErrorMessage(err, t("Ma'lumotlarni yuklab bo'lmadi"))))
            .finally(() => !cancelled && setLoading(false));

        return () => {
            cancelled = true;
        };
    }, [farmId, filters, reloadKey]);

    // Hayvon guruhlari (sotuvda sotilgan hayvonlar sonini guruhdan ayirish uchun)
    useEffect(() => {
        let cancelled = false;
        api.get("animals-group/", { params: { farm: farmId, status: "faol" } })
            .then(({ data }) => !cancelled && setGroups(asList(data)))
            .catch(() => {}); // guruhlar yuklanmasa ham kirim-chiqim ishlayveradi
        return () => {
            cancelled = true;
        };
    }, [farmId, reloadKey]);

    // Kunlik/oylik/yillik hisobot (filtrlar va yangi yozuvlar bilan birga yangilanadi)
    useEffect(() => {
        let cancelled = false;
        const params = { farm: farmId, period: reportPeriod };
        Object.entries(filters).forEach(([k, v]) => {
            if (v) params[k] = v;
        });

        api.get("finance/report/", { params })
            .then(({ data }) => {
                if (cancelled) return;
                setReport(data);
                setReportError("");
            })
            .catch((err) => !cancelled && setReportError(getErrorMessage(err, t("Hisobotni yuklab bo'lmadi"))));

        return () => {
            cancelled = true;
        };
    }, [farmId, filters, reloadKey, reportPeriod]);

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

    // Hayvon sotuvi: faqat "Kirim" + "Sotuv" bo'lsa va fermada hayvon guruhi bo'lsa
    const isSale = form.transaction_type === "kirim" && form.category === "sotuv";
    const selectedGroup = groups.find((g) => String(g.id) === form.animal_group);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setFormError("");
        setFormNotice("");
        setSaving(true);
        try {
            const payload = {
                farm: Number(farmId),
                transaction_type: form.transaction_type,
                category: form.category,
                amount: form.amount,
                date: form.date,
                description: form.description.trim(),
            };
            if (isSale && form.animal_group) {
                payload.animal_group = Number(form.animal_group);
                if (form.animal_count) payload.animal_count = Number(form.animal_count);
            }
            Object.assign(payload, creditPayload(credit));
            await api.post("finance/", payload);
            // tur va kategoriya saqlanadi, summa va izoh tozalanadi (ketma-ket kiritish qulay bo'lsin)
            setForm((prev) => ({ ...prev, amount: "", description: "", animal_group: "", animal_count: "" }));
            if (credit.on_credit) {
                setFormNotice(t('Nasiya yozildi: u "Qarzlar" sahifasida turadi. Pul to\'langanda balansga qo\'shiladi.'));
            }
            setCredit(EMPTY_CREDIT());
            reload();
        } catch (err) {
            setFormError(getErrorMessage(err, t("Saqlashda xatolik yuz berdi")));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (tx) => {
        const label = `${t(TYPES[tx.transaction_type])}: ${formatMoney(tx.amount)}`;
        const back = tx.animal_count
            ? `\n\n${t('{count} ta {name} guruhga qaytariladi.', { count: tx.animal_count, name: tx.animal_group_label || t("hayvon") })}`
            : "";
        if (!window.confirm(`${t("Bu yozuv o'chirilsinmi?")}\n${label}${back}`)) return;
        try {
            await api.delete(`finance/${tx.id}/`);
            reload();
        } catch (err) {
            setError(getErrorMessage(err, t("O'chirib bo'lmadi")));
        }
    };

    const hasFilters = Object.values(filters).some(Boolean);

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>{t('FarmLine')}</h1>
                <div className="user-bar">
                    <span>{t('Salom, {name}!', { name: user.first_name || user.username })}</span>
                    <LanguageSwitcher />
                    <NotificationBell />
                    <Link to="/profile" className="user-link">{t('Profil')}</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={logout}>{t('Chiqish')}</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">{t('← Fermalarga qaytish')}</Link>

                {farmError ? (
                    <p className="error-text">{farmError}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm ? farm.name : "..."}: {t('kirim-chiqim')}</h2>
                        {farm && <p className="panel-subtitle">{farm.location}</p>}

                        {/* Jamlanma */}
                        <div className="stat-grid stat-grid--3">
                            <div className="stat-card">
                                <span className="stat-value amount-in">{formatMoney(summary?.income)}</span>
                                <span className="stat-label">{t('Jami kirim')}</span>
                            </div>
                            <div className="stat-card">
                                <span className="stat-value amount-out">{formatMoney(summary?.expense)}</span>
                                <span className="stat-label">{t('Jami chiqim')}</span>
                            </div>
                            <div className="stat-card">
                                <span className={`stat-value ${Number(summary?.balance) < 0 ? "amount-out" : ""}`}>
                                    {formatMoney(summary?.balance)}
                                </span>
                                <span className="stat-label">{t('Balans')}</span>
                            </div>
                        </div>

                        {/* Foyda / zarar hisoboti */}
                        <h3 className="section-title">{t('Foyda va zarar')}</h3>
                        <div className="period-tabs">
                            {[["day", t("Kunlik")], ["week", t("Haftalik")], ["month", t("Oylik")], ["year", t("Yillik")]].map(([v, l]) => (
                                <button key={v} type="button"
                                    className={`btn-ghost ${reportPeriod === v ? "is-active" : ""}`}
                                    onClick={() => setReportPeriod(v)}>
                                    {l}
                                </button>
                            ))}
                        </div>
                        {reportError ? (
                            <p className="error-text">{reportError}</p>
                        ) : report.length === 0 ? (
                            <p className="empty-state">{t("Hisobot uchun yozuvlar yo'q")}</p>
                        ) : (
                            <div className="report-wrap">
                                <table className="report-table report-table--money">
                                    <thead>
                                        <tr>
                                            <th>{t('Davr')}</th>
                                            <th>{t('Kirim')}</th>
                                            <th>{t('Chiqim')}</th>
                                            <th>{t('Foyda / zarar')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {report.map((r) => (
                                            <tr key={r.period}>
                                                <td>{formatPeriod(r.period, reportPeriod)}</td>
                                                <td className="amount-in"><Money value={r.income} /></td>
                                                <td className="amount-out"><Money value={r.expense} /></td>
                                                <td className={Number(r.profit) < 0 ? "amount-out" : "amount-in"}>
                                                    <strong>
                                                        {Number(r.profit) > 0 ? "+" : ""}<Money value={r.profit} />
                                                    </strong>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {/* Oylik hisobotni Excel/PDF qilib yuklab olish */}
                        <ReportDownload farmId={farmId} />

                        {/* Yangi yozuv */}
                        <form className="farm-form" onSubmit={handleSubmit}>
                            <h3>{t("Yangi yozuv qo'shish")}</h3>
                            <div className="form-row">
                                <div className="form-field">
                                    <label htmlFor="tx-type">{t('Turi')}</label>
                                    <select id="tx-type" name="transaction_type" value={form.transaction_type}
                                        onChange={handleFormChange}>
                                        {Object.entries(TYPES).map(([k, v]) => [k, t(v)]).map(([v, l]) => (
                                            <option key={v} value={v}>{t(l)}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-field">
                                    <label htmlFor="tx-category">{t('Kategoriya')}</label>
                                    <select id="tx-category" name="category" value={form.category}
                                        onChange={handleFormChange}>
                                        {Object.entries(CATEGORIES).map(([k, v]) => [k, t(v)]).map(([v, l]) => (
                                            <option key={v} value={v}>{l}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <div className="form-row">
                                <div className="form-field">
                                    <label htmlFor="tx-amount">{t("Summa (so'm)")}</label>
                                    <input id="tx-amount" type="number" name="amount" min="0.01" step="0.01"
                                        inputMode="decimal" value={form.amount} onChange={handleFormChange} required />
                                </div>
                                <div className="form-field">
                                    <label htmlFor="tx-date">{t('Sana')}</label>
                                    <input id="tx-date" type="date" name="date" value={form.date}
                                        onChange={handleFormChange} required />
                                </div>
                            </div>
                            {isSale && groups.length > 0 && (
                                <div className="form-row">
                                    <div className="form-field">
                                        <label htmlFor="tx-group">{t("Qaysi hayvonlar sotildi (ixtiyoriy)")}</label>
                                        <select id="tx-group" name="animal_group" value={form.animal_group}
                                            onChange={handleFormChange}>
                                            <option value="">{t("Hayvon sonini hisobga olmaslik")}</option>
                                            {groups.map((g) => (
                                                <option key={g.id} value={g.id}>
                                                    {g.animal_type_name}{g.breed ? ` (${g.breed})` : ""} — {t('{count} ta', { count: g.count })}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    {selectedGroup && (
                                        <div className="form-field">
                                            <label htmlFor="tx-count">{t('Sotilgan soni')}</label>
                                            <input id="tx-count" type="number" name="animal_count" min="1" step="1"
                                                max={selectedGroup.count} value={form.animal_count}
                                                onChange={handleFormChange} required />
                                        </div>
                                    )}
                                </div>
                            )}
                            {isSale && selectedGroup && (
                                <p className="workers-hint">
                                    {t('Guruhda hozir {count} ta bor. Saqlaganingizda sotilgan soni avtomatik ayriladi.', { count: selectedGroup.count })}
                                </p>
                            )}
                            <CreditFields farmId={farmId} kind={form.transaction_type === "kirim" ? "mijoz" : "taminotchi"}
                                total={form.amount} value={credit} onChange={setCredit} />
                            <div className="form-field">
                                <label htmlFor="tx-desc">{t("Izoh (ixtiyoriy)")}</label>
                                <input id="tx-desc" type="text" name="description" value={form.description}
                                    onChange={handleFormChange} />
                            </div>
                            {formError && <p className="error-text" role="alert">{formError}</p>}
                            {formNotice && <p className="workers-hint" role="status">{formNotice}</p>}
                            <button type="submit" className="btn-primary" disabled={saving}>
                                {saving ? t("Saqlanmoqda...") : t("Saqlash")}
                            </button>
                        </form>

                        {/* Filtrlar */}
                        <h3 className="section-title">{t('Yozuvlar')}</h3>
                        <div className="filter-bar">
                            <select name="transaction_type" value={filters.transaction_type}
                                onChange={handleFilter} aria-label={t("Turi bo'yicha filtr")}>
                                <option value="">{t("Barcha turlar")}</option>
                                {Object.entries(TYPES).map(([k, v]) => [k, t(v)]).map(([v, l]) => (
                                    <option key={v} value={v}>{l}</option>
                                ))}
                            </select>
                            <select name="category" value={filters.category}
                                onChange={handleFilter} aria-label={t("Kategoriya bo'yicha filtr")}>
                                <option value="">{t("Barcha kategoriyalar")}</option>
                                {Object.entries(CATEGORIES).map(([k, v]) => [k, t(v)]).map(([v, l]) => (
                                    <option key={v} value={v}>{l}</option>
                                ))}
                            </select>
                            <input type="date" name="date_from" value={filters.date_from}
                                onChange={handleFilter} aria-label={t("Boshlanish sanasi")} />
                            <input type="date" name="date_to" value={filters.date_to}
                                onChange={handleFilter} aria-label={t("Tugash sanasi")} />
                            {hasFilters && (
                                <button type="button" className="btn-ghost" onClick={clearFilters}>{t('Tozalash')}</button>
                            )}
                        </div>

                        {/* Ro'yxat */}
                        {loading ? (
                            <p className="empty-state">{t("Yuklanmoqda...")}</p>
                        ) : error ? (
                            <div className="empty-state">
                                <p className="error-text">{error}</p>
                                <button className="btn-ghost" onClick={reload}>{t("Qayta urinish")}</button>
                            </div>
                        ) : transactions.length === 0 ? (
                            <p className="empty-state">
                                {hasFilters ? t("Hech narsa topilmadi") : t("Hali yozuvlar yo'q")}
                            </p>
                        ) : (
                            <ul className="tx-list">
                                {transactions.map((tx) => (
                                    <li key={tx.id} className={`tx-item tx-item--${tx.transaction_type}`}>
                                        <div className="tx-main">
                                            <span className="tx-category">{t(CATEGORIES[tx.category]) ? t(CATEGORIES[tx.category]) : tx.category}</span>
                                            <span className="tx-meta">
                                                {tx.date}
                                                {tx.animal_count ? ` · ${t('{count} ta {name} sotildi', { count: tx.animal_count, name: tx.animal_group_label || t("hayvon") })}` : ""}
                                                {tx.description ? t(' · {description}', { description: tx.description }) : ""}
                                            </span>
                                        </div>
                                        <div className="tx-side">
                                            <span className={`tx-amount ${tx.transaction_type === "kirim" ? "amount-in" : "amount-out"}`}>
                                                {tx.transaction_type === "kirim" ? "+" : "−"}{formatMoney(tx.amount)}
                                            </span>
                                            <button type="button" className="tx-delete" onClick={() => handleDelete(tx)}
                                                aria-label={t("Yozuvni o'chirish")}>
                                                {t("O'chirish")}
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
