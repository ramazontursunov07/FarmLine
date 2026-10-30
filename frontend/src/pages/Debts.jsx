import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatMoney, today } from '../utils/format';
import InstallButton from '../components/InstallButton';
import NotificationBell from '../components/NotificationBell';

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const KINDS = {
    mijoz: {
        tab: 'Mijozlar',
        who: 'Mijoz',
        owes: 'Sizga qarzdor',
        addParty: "+ Mijoz qo'shish",
        hint: 'Sut yoki boshqa mahsulotni nasiyaga olganlar. Ular sizga qarzdor.',
    },
    taminotchi: {
        tab: 'Yetkazib beruvchilar',
        who: 'Yetkazib beruvchi',
        owes: 'Siz qarzdorsiz',
        addParty: "+ Yetkazib beruvchi qo'shish",
        hint: 'Yem yoki boshqa narsani nasiyaga berganlar. Siz ularga qarzdorsiz.',
    },
};

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

function addDays(iso, days) {
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(y, m - 1, d + days);
    const pad = (x) => String(x).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

const EMPTY_DEBT = () => ({ party: '', new_name: '', amount: '', date: today(), due_date: addDays(today(), 7), description: '' });

function Debts() {
    const { farmId } = useParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [kind, setKind] = useState('mijoz');
    const [parties, setParties] = useState([]);
    const [debts, setDebts] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);

    const [onlyOpen, setOnlyOpen] = useState(false);
    const [onlyOverdue, setOnlyOverdue] = useState(false);
    const [openParty, setOpenParty] = useState(null);

    const [showDebtForm, setShowDebtForm] = useState(false);
    const [debtForm, setDebtForm] = useState(EMPTY_DEBT());
    const [debtError, setDebtError] = useState('');
    const [showPartyForm, setShowPartyForm] = useState(false);
    const [partyForm, setPartyForm] = useState({ name: '', phone: '' });
    const [partyError, setPartyError] = useState('');
    const [payForm, setPayForm] = useState({ debt: null, amount: '', date: today() });
    const [payError, setPayError] = useState('');
    const [busy, setBusy] = useState(false);

    const reload = () => setReloadKey((k) => k + 1);
    const L = KINDS[kind];

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        (async () => {
            try {
                const farmRes = await api.get(`farms/${farmId}/`);
                if (!farmRes.data.can_view_finance) {
                    if (!cancelled) {
                        setFarm(farmRes.data);
                        setError("Qarzlarni ko'rishga ruxsat yo'q");
                    }
                    return;
                }
                const [partiesRes, debtsRes, summaryRes] = await Promise.all([
                    api.get('debt-party/', { params: { farm: farmId, kind } }),
                    api.get('debt/', { params: { farm: farmId, kind } }),
                    api.get('debt/summary/', { params: { farm: farmId } }),
                ]);
                if (cancelled) return;
                setFarm(farmRes.data);
                setParties(asList(partiesRes.data));
                setDebts(asList(debtsRes.data));
                setSummary(summaryRes.data);
                setError('');
            } catch (err) {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? 'Ferma topilmadi' : getErrorMessage(err, "Qarzlarni yuklab bo'lmadi"));
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [farmId, kind, reloadKey]);

    const debtsByParty = useMemo(() => {
        const map = {};
        debts.forEach((d) => {
            (map[d.party] || (map[d.party] = [])).push(d);
        });
        return map;
    }, [debts]);

    const rowsShown = useMemo(() => parties
        .filter((p) => {
            const t = p.totals;
            if (onlyOverdue) return t && t.overdue_count > 0;
            if (onlyOpen) return t && Number(t.remaining) > 0;
            return true;
        })
        // Eng muhimi tepada: avval muddati o'tganlar (summasi katta bo'yicha), keyin qoldig'i katta bo'yicha
        .sort((a, b) => {
            const ao = Number(a.totals?.overdue_amount || 0);
            const bo = Number(b.totals?.overdue_amount || 0);
            if (ao !== bo) return bo - ao;
            return Number(b.totals?.remaining || 0) - Number(a.totals?.remaining || 0);
        }), [parties, onlyOpen, onlyOverdue]);

    const run = async (fn, setErr, fallback) => {
        setBusy(true);
        setErr('');
        try {
            await fn();
            reload();
            return true;
        } catch (err) {
            setErr(getErrorMessage(err, fallback));
            return false;
        } finally {
            setBusy(false);
        }
    };

    const handleAddParty = async (e) => {
        e.preventDefault();
        const ok = await run(
            () => api.post('debt-party/', {
                farm: Number(farmId), kind, name: partyForm.name.trim(), phone: partyForm.phone.trim(),
            }),
            setPartyError,
            "Saqlab bo'lmadi"
        );
        if (ok) {
            setPartyForm({ name: '', phone: '' });
            setShowPartyForm(false);
            // Yangi odamning hali qarzi yo'q: filtr uni yashirib qo'ymasin
            setOnlyOpen(false);
            setOnlyOverdue(false);
        }
    };

    const handleAddDebt = async (e) => {
        e.preventDefault();
        const ok = await run(async () => {
            let partyId = debtForm.party;
            if (partyId === 'new') {
                const name = debtForm.new_name.trim();
                if (!name) throw new Error("Ismni kiriting");
                const { data } = await api.post('debt-party/', { farm: Number(farmId), kind, name });
                partyId = data.id;
            }
            if (!partyId) throw new Error(`${L.who}ni tanlang`);
            await api.post('debt/', {
                party: Number(partyId),
                amount: debtForm.amount,
                date: debtForm.date,
                due_date: debtForm.due_date || null,
                description: debtForm.description.trim(),
            });
            setOpenParty(Number(partyId));
        }, setDebtError, "Qarzni saqlab bo'lmadi");
        if (ok) {
            setDebtForm(EMPTY_DEBT());
            setShowDebtForm(false);
        }
    };

    const handlePay = async (e, debt) => {
        e.preventDefault();
        const ok = await run(
            () => api.post('debt-payment/', { debt: debt.id, amount: payForm.amount, date: payForm.date }),
            setPayError,
            "To'lovni saqlab bo'lmadi"
        );
        if (ok) setPayForm({ debt: null, amount: '', date: today() });
    };

    const startPay = (debt, full = false) => {
        setPayError('');
        setPayForm({ debt: debt.id, amount: full ? debt.remaining : '', date: today() });
    };

    const handleDeletePayment = async (p) => {
        if (!window.confirm(`${formatMoney(p.amount)} to'lovni o'chirasizmi?\n\nQarz qoldig'i shuncha oshadi.`)) return;
        try {
            await api.delete(`debt-payment/${p.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleDeleteDebt = async (d) => {
        const extra = d.affects_balance
            ? "\n\nBu qarz sotuv/xarid bilan bog'liq: to'langan pullar balansdan ham olib tashlanadi" +
              "\n(sotilgan hayvonlar bo'lsa, guruhga qaytadi). Sut sotuvi bo'lsa, uni sut sahifasidan bekor qilish to'g'riroq."
            : '';
        if (!window.confirm(`${formatMoney(d.amount)} qarzni o'chirasizmi?\n\nUning barcha to'lovlari ham o'chadi. Buni qaytarib bo'lmaydi.${extra}`)) return;
        try {
            await api.delete(`debt/${d.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleDeleteParty = async (p) => {
        if (!window.confirm(`${p.name} ro'yxatdan o'chirilsinmi?`)) return;
        try {
            await api.delete(`debt-party/${p.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const recv = summary?.receivable;
    const pay = summary?.payable;
    const overdueCount = (recv?.overdue_count || 0) + (pay?.overdue_count || 0);
    const overdueSum = Number(recv?.overdue_amount || 0) + Number(pay?.overdue_amount || 0);
    const paidTotal = Number(recv?.paid || 0) + Number(pay?.paid || 0);

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <NotificationBell />
                    <Link to="/profile" className="user-link">Profil</Link>
                    <InstallButton />
                    <button className="btn-ghost" onClick={logout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">← Fermalarga qaytish</Link>

                {loading && !farm ? (
                    <p className="empty-state">Yuklanmoqda...</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm.name}: qarzlar</h2>
                        <p className="panel-subtitle">
                            Kim sizga qancha qarz, siz kimga qarzdorsiz va qaysi muddat o'tib ketgan.
                            Muddati o'tgan qarzlar haqida Telegramdan har kuni eslatma keladi.
                        </p>

                        <div className="stat-grid">
                            <div className="stat-card">
                                <span className="stat-value">{formatMoney(recv?.remaining)}</span>
                                <span className="stat-label">Sizga qarzdorlar (mijozlar)</span>
                            </div>
                            <div className="stat-card">
                                <span className="stat-value">{formatMoney(pay?.remaining)}</span>
                                <span className="stat-label">Siz qarzdorsiz (yetkazib beruvchilar)</span>
                            </div>
                            <div className={`stat-card${overdueCount > 0 ? ' stat-card--warn' : ''}`}>
                                <span className="stat-value">{overdueCount} ta</span>
                                <span className="stat-label">Muddati o'tgan</span>
                                {overdueCount > 0 && <span className="stat-sub">{formatMoney(overdueSum)}</span>}
                            </div>
                            <div className="stat-card">
                                <span className="stat-value">{formatMoney(paidTotal)}</span>
                                <span className="stat-label">Shu paytgacha to'langan</span>
                            </div>
                        </div>

                        <div className="filter-bar">
                            {Object.entries(KINDS).map(([k, v]) => (
                                <button key={k} type="button"
                                    className={k === kind ? 'btn-primary btn-auto' : 'btn-ghost'}
                                    onClick={() => { setKind(k); setOpenParty(null); setShowDebtForm(false); setShowPartyForm(false); }}>
                                    {v.tab}
                                </button>
                            ))}
                        </div>
                        <p className="workers-hint">{L.hint}</p>

                        <div className="filter-bar">
                            <button type="button" className="btn-primary btn-auto"
                                onClick={() => { setDebtError(''); setDebtForm({ ...EMPTY_DEBT(), party: parties[0] ? String(parties[0].id) : 'new' }); setShowDebtForm((v) => !v); }}>
                                + Qarz yozish
                            </button>
                            <button type="button" className="btn-ghost"
                                onClick={() => { setPartyError(''); setShowPartyForm((v) => !v); }}>
                                {L.addParty}
                            </button>
                        </div>

                        {showPartyForm && (
                            <div className="work-card">
                                <form className="animal-inline-form" onSubmit={handleAddParty}>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Ism</label>
                                            <input type="text" value={partyForm.name} maxLength={120} required
                                                onChange={(e) => setPartyForm({ ...partyForm, name: e.target.value })} />
                                        </div>
                                        <div className="form-field">
                                            <label>Telefon (ixtiyoriy)</label>
                                            <input type="tel" value={partyForm.phone} maxLength={30}
                                                onChange={(e) => setPartyForm({ ...partyForm, phone: e.target.value })} />
                                        </div>
                                    </div>
                                    {partyError && <p className="error-text" role="alert">{partyError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>Saqlash</button>
                                </form>
                            </div>
                        )}

                        {showDebtForm && (
                            <div className="work-card">
                                <form className="animal-inline-form" onSubmit={handleAddDebt}>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>{L.who}</label>
                                            <select value={debtForm.party}
                                                onChange={(e) => setDebtForm({ ...debtForm, party: e.target.value })}>
                                                {parties.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                                                <option value="new">+ Yangi odam</option>
                                            </select>
                                        </div>
                                        {debtForm.party === 'new' && (
                                            <div className="form-field">
                                                <label>Yangi odam ismi</label>
                                                <input type="text" value={debtForm.new_name} maxLength={120}
                                                    onChange={(e) => setDebtForm({ ...debtForm, new_name: e.target.value })} />
                                            </div>
                                        )}
                                    </div>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Summa (so'm)</label>
                                            <input type="number" min="1" step="any" value={debtForm.amount} required
                                                onChange={(e) => setDebtForm({ ...debtForm, amount: e.target.value })} />
                                        </div>
                                        <div className="form-field">
                                            <label>Izoh</label>
                                            <input type="text" value={debtForm.description} maxLength={200}
                                                placeholder={kind === 'mijoz' ? 'Masalan: 120 litr sut' : 'Masalan: 500 kg omuxta yem'}
                                                onChange={(e) => setDebtForm({ ...debtForm, description: e.target.value })} />
                                        </div>
                                    </div>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Berilgan sana</label>
                                            <input type="date" value={debtForm.date} max={today()} required
                                                onChange={(e) => setDebtForm({ ...debtForm, date: e.target.value })} />
                                        </div>
                                        <div className="form-field">
                                            <label>To'lash muddati</label>
                                            <input type="date" value={debtForm.due_date} min={debtForm.date}
                                                onChange={(e) => setDebtForm({ ...debtForm, due_date: e.target.value })} />
                                        </div>
                                    </div>
                                    {debtError && <p className="error-text" role="alert">{debtError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>Qarzni saqlash</button>
                                </form>
                            </div>
                        )}

                        <div className="filter-bar">
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                                <input type="checkbox" checked={onlyOpen && !onlyOverdue} disabled={onlyOverdue}
                                    style={{ width: 'auto', margin: 0 }}
                                    onChange={(e) => setOnlyOpen(e.target.checked)} />
                                Faqat qarzi borlar
                            </label>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                                <input type="checkbox" checked={onlyOverdue}
                                    style={{ width: 'auto', margin: 0 }}
                                    onChange={(e) => setOnlyOverdue(e.target.checked)} />
                                Faqat muddati o'tganlar
                            </label>
                        </div>

                        {rowsShown.length === 0 ? (
                            <p className="empty-state">
                                {parties.length === 0 ? `Hozircha ${L.who.toLowerCase()} yo'q` : "Bunday yozuv yo'q"}
                            </p>
                        ) : (
                            <div className="report-wrap">
                                <table className="report-table">
                                    <thead>
                                        <tr>
                                            <th>{L.who}</th>
                                            <th>Jami qarz</th>
                                            <th>To'langan</th>
                                            <th>Qoldi</th>
                                            <th>Muddati o'tgan</th>
                                            <th />
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rowsShown.map((p) => {
                                            const t = p.totals || {};
                                            const isOpen = openParty === p.id;
                                            return (
                                                <PartyRows key={p.id} p={p} t={t} isOpen={isOpen} kind={kind}
                                                    debts={debtsByParty[p.id] || []}
                                                    onToggle={() => setOpenParty(isOpen ? null : p.id)}
                                                    onDeleteParty={() => handleDeleteParty(p)}
                                                    onDeleteDebt={handleDeleteDebt}
                                                    onDeletePayment={handleDeletePayment}
                                                    payForm={payForm} setPayForm={setPayForm} payError={payError}
                                                    startPay={startPay} onPay={handlePay} busy={busy} />
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}

function PartyRows({ p, t, isOpen, kind, debts, onToggle, onDeleteParty, onDeleteDebt, onDeletePayment,
    payForm, setPayForm, payError, startPay, onPay, busy }) {
    const hasOverdue = (t.overdue_count || 0) > 0;
    return (
        <>
            <tr>
                <td>
                    <strong>{p.name}</strong>
                    {p.phone && <div className="work-meta">{p.phone}</div>}
                </td>
                <td>{formatMoney(t.amount)}</td>
                <td>{formatMoney(t.paid)}</td>
                <td><strong>{formatMoney(t.remaining)}</strong></td>
                <td>
                    {hasOverdue
                        ? <span className="work-badge work-badge--shoshilinch">{t.overdue_count} ta · {formatMoney(t.overdue_amount)}</span>
                        : '—'}
                </td>
                <td>
                    <button type="button" className="btn-ghost" onClick={onToggle}>
                        {isOpen ? 'Yopish' : 'Ochish'}
                    </button>
                </td>
            </tr>
            {isOpen && (
                <tr>
                    <td colSpan={6}>
                        {debts.length === 0 ? (
                            <p className="work-meta">Bu odamning qarz yozuvi yo'q.</p>
                        ) : (
                            <ul className="work-list">
                                {debts.map((d) => (
                                    <li key={d.id} className="work-item" style={{ display: 'block' }}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                {formatMoney(d.amount)}{d.description ? ` · ${d.description}` : ''}
                                                {Number(d.remaining) === 0 && <span className="work-badge">To'langan</span>}
                                                {d.is_overdue && (
                                                    <span className="work-badge work-badge--shoshilinch">{d.days_overdue} kun kechikdi</span>
                                                )}
                                                {d.affects_balance && <span className="work-badge work-badge--credit">Balansga ta'sir qiladi</span>}
                                            </span>
                                            <span className="work-meta">
                                                Berilgan: {formatDate(d.date)}
                                                {d.due_date ? ` · muddat: ${formatDate(d.due_date)}` : ' · muddatsiz'}
                                                {' · '}to'langan: {formatMoney(d.paid)} · qoldi: <strong>{formatMoney(d.remaining)}</strong>
                                            </span>
                                            {d.payments.length > 0 && (
                                                <ul className="work-list">
                                                    {d.payments.map((pay) => (
                                                        <li key={pay.id} className="work-meta">
                                                            {formatDate(pay.date)}: {formatMoney(pay.amount)}{' '}
                                                            <button type="button" className="db-link-btn db-link-btn--danger"
                                                                onClick={() => onDeletePayment(pay)}>o'chirish</button>
                                                        </li>
                                                    ))}
                                                </ul>
                                            )}
                                        </div>

                                        {payForm.debt === d.id ? (
                                            <form className="animal-inline-form" onSubmit={(e) => onPay(e, d)}>
                                                <div className="form-row">
                                                    <div className="form-field">
                                                        <label>To'lov summasi</label>
                                                        <input type="number" min="1" step="any" max={d.remaining} required
                                                            value={payForm.amount}
                                                            onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} />
                                                    </div>
                                                    <div className="form-field">
                                                        <label>Sana</label>
                                                        <input type="date" value={payForm.date} max={today()} min={d.date} required
                                                            onChange={(e) => setPayForm({ ...payForm, date: e.target.value })} />
                                                    </div>
                                                </div>
                                                {d.affects_balance && (
                                                    <p className="workers-hint">
                                                        {kind === 'mijoz'
                                                            ? "Bu to'lov balansga kirim bo'lib qo'shiladi."
                                                            : "Bu to'lov balansdan chiqim bo'lib ayriladi."}
                                                    </p>
                                                )}
                                                {payError && <p className="error-text" role="alert">{payError}</p>}
                                                <div className="animal-actions">
                                                    <button type="submit" className="btn-primary btn-auto" disabled={busy}>To'lovni saqlash</button>
                                                    <button type="button" className="btn-ghost"
                                                        onClick={() => setPayForm({ debt: null, amount: '', date: today() })}>
                                                        Bekor qilish
                                                    </button>
                                                </div>
                                            </form>
                                        ) : (
                                            <div className="animal-actions">
                                                {Number(d.remaining) > 0 && (
                                                    <>
                                                        <button type="button" className="btn-ghost" onClick={() => startPay(d)}>
                                                            + To'lov
                                                        </button>
                                                        <button type="button" className="btn-ghost" onClick={() => startPay(d, true)}>
                                                            To'liq to'landi
                                                        </button>
                                                    </>
                                                )}
                                                <button type="button" className="farm-item-action farm-item-action--danger"
                                                    onClick={() => onDeleteDebt(d)}>
                                                    Qarzni o'chirish
                                                </button>
                                            </div>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                        <button type="button" className="db-link-btn db-link-btn--danger" onClick={onDeleteParty}>
                            {p.name} ni ro'yxatdan o'chirish
                        </button>
                    </td>
                </tr>
            )}
        </>
    );
}

export default Debts;
