import { useState, useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';

const ITEM_TYPES = { ozuqa: 'Ozuqa', dori: 'Dori-darmon', boshqa: 'Boshqa' };
const TX_TYPES = { sarf: 'Sarf (ishlatildi)', kirim: 'Kirim (olib kelindi)' };

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

const qty = (value) => Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 });

function formatDate(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.slice(0, 10).split('-');
    return `${d}.${m}.${y}`;
}

const EMPTY_ITEM = { item_name: '', item_type: 'ozuqa', unit: 'kg', quantity: '0', low_stock_threshold: '0' };
const makeTx = () => ({ inventory_item: '', transaction_type: 'sarf', quantity: '', date: today(), note: '' });
const EMPTY_FILTERS = { inventory_item: '', transaction_type: '' };

function Inventory() {
    const { farmId } = useParams();
    const { user, logout } = useAuth();

    const [farm, setFarm] = useState(null);
    const [items, setItems] = useState([]);
    const [txs, setTxs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [reloadKey, setReloadKey] = useState(0);

    const [itemForm, setItemForm] = useState(EMPTY_ITEM);
    const [itemError, setItemError] = useState('');
    const [savingItem, setSavingItem] = useState(false);

    const [txForm, setTxForm] = useState(makeTx);
    const [txError, setTxError] = useState('');
    const [savingTx, setSavingTx] = useState(false);

    const [filters, setFilters] = useState(EMPTY_FILTERS);

    const reload = () => setReloadKey((k) => k + 1);

    useEffect(() => {
        let cancelled = false;
        Promise.all([
            api.get(`farms/${farmId}/`),
            api.get('inventory-item/', { params: { farm: farmId } }),
            api.get('inventory-transaction/', { params: { farm: farmId } }),
        ])
            .then(([farmRes, itemsRes, txRes]) => {
                if (cancelled) return;
                setFarm(farmRes.data);
                setItems(asList(itemsRes.data));
                setTxs(asList(txRes.data));
                setError('');
            })
            .catch((err) => {
                if (!cancelled) {
                    setError(err.response?.status === 404 ? 'Ferma topilmadi' : getErrorMessage(err, "Omborni yuklab bo'lmadi"));
                }
            })
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, [farmId, reloadKey]);

    const isOwner = farm ? farm.owner_username === user.username : false;
    const roleLabel = (userId) => (farm && userId === farm.owner ? 'Fermer' : 'Ishchi');

    // Zaxirasi kam qolganlar birinchi
    const sortedItems = useMemo(
        () => [...items].sort((a, b) => Number(b.is_low_stock) - Number(a.is_low_stock) || a.item_name.localeCompare(b.item_name)),
        [items]
    );
    const lowCount = items.filter((i) => i.is_low_stock).length;

    const selectedItemId = txForm.inventory_item || (sortedItems[0] ? String(sortedItems[0].id) : '');
    const selectedItem = items.find((i) => String(i.id) === selectedItemId);

    const history = useMemo(
        () =>
            txs.filter(
                (t) =>
                    (!filters.inventory_item || String(t.inventory_item) === filters.inventory_item) &&
                    (!filters.transaction_type || t.transaction_type === filters.transaction_type)
            ),
        [txs, filters]
    );

    const handleItemChange = (e) => setItemForm({ ...itemForm, [e.target.name]: e.target.value });
    const handleTxChange = (e) => setTxForm({ ...txForm, [e.target.name]: e.target.value });

    const handleAddItem = async (e) => {
        e.preventDefault();
        setSavingItem(true);
        setItemError('');
        try {
            await api.post('inventory-item/', { ...itemForm, farm: Number(farmId) });
            setItemForm(EMPTY_ITEM);
            reload();
        } catch (err) {
            setItemError(getErrorMessage(err, "Mahsulotni qo'shib bo'lmadi"));
        } finally {
            setSavingItem(false);
        }
    };

    const handleAddTx = async (e) => {
        e.preventDefault();
        setSavingTx(true);
        setTxError('');
        try {
            await api.post('inventory-transaction/', { ...txForm, inventory_item: Number(selectedItemId) });
            setTxForm({ ...makeTx(), inventory_item: selectedItemId, transaction_type: txForm.transaction_type });
            reload();
        } catch (err) {
            setTxError(getErrorMessage(err, "Yozuvni saqlab bo'lmadi"));
        } finally {
            setSavingTx(false);
        }
    };

    // Mahsulot kartochkasidagi "Sarf" / "Kirim" tugmalari: formani tanlab, unga o'tkazadi
    const quickTx = (item, type) => {
        setTxForm({ ...makeTx(), inventory_item: String(item.id), transaction_type: type });
        setTxError('');
        document.getElementById('inventory-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    const handleThreshold = async (item) => {
        const value = window.prompt(
            `"${item.item_name}": zaxira qancha (${item.unit}) dan kam qolganda ogohlantirilsin?`,
            item.low_stock_threshold
        );
        if (value === null) return;
        const n = Number(value);
        if (value.trim() === '' || Number.isNaN(n) || n < 0) {
            window.alert("Iltimos, 0 yoki undan katta son kiriting");
            return;
        }
        try {
            await api.patch(`inventory-item/${item.id}/`, { low_stock_threshold: n });
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'zgartirib bo'lmadi"));
        }
    };

    const handleDeleteItem = async (item) => {
        const ok = window.confirm(
            `"${item.item_name}" mahsulotini o'chirasizmi?\n\nUning barcha kirim-sarf tarixi ham o'chib ketadi. Buni qaytarib bo'lmaydi.`
        );
        if (!ok) return;
        try {
            await api.delete(`inventory-item/${item.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    const handleDeleteTx = async (t) => {
        const ok = window.confirm(
            `Bu yozuvni o'chirasizmi?\n\n${t.transaction_type_display}: ${qty(t.quantity)} ${t.inventory_unit} (${t.inventory_name})\n` +
            'Zaxira avtomatik tuzatiladi.'
        );
        if (!ok) return;
        try {
            await api.delete(`inventory-transaction/${t.id}/`);
            reload();
        } catch (err) {
            window.alert(getErrorMessage(err, "O'chirib bo'lmadi"));
        }
    };

    return (
        <div className="app-shell">
            <header className="app-header">
                <h1>FarmLine</h1>
                <div className="user-bar">
                    <span>Salom, {user.first_name || user.username}!</span>
                    <Link to="/profile" className="user-link">Profil</Link>
                    <button className="btn-ghost" onClick={logout}>Chiqish</button>
                </div>
            </header>

            <main className="app-main">
                <Link to="/dashboard" className="back-link">← Fermalarga qaytish</Link>

                {loading ? (
                    <p className="empty-state">Yuklanmoqda...</p>
                ) : error ? (
                    <p className="error-text">{error}</p>
                ) : (
                    <>
                        <h2 className="panel-title">{farm.name}: ombor</h2>
                        <p className="panel-subtitle">
                            {lowCount > 0 ? (
                                <span className="task-overdue">{lowCount} ta mahsulot zaxirasi kam qolgan</span>
                            ) : (
                                'Ozuqa, dori va boshqa mahsulotlar zaxirasi'
                            )}
                        </p>

                        {/* Zaxira */}
                        <h3 className="section-title">Zaxira</h3>
                        {sortedItems.length === 0 ? (
                            <p className="empty-state">
                                {isOwner
                                    ? "Omborda hali mahsulot yo'q. Pastdagi formadan qo'shing."
                                    : "Fermer hali omborga mahsulot qo'shmagan."}
                            </p>
                        ) : (
                            <ul className="work-list">
                                {sortedItems.map((item) => (
                                    <li key={item.id} className={`work-item${item.is_low_stock ? ' work-item--overdue' : ''}`}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                {item.item_name}
                                                <span className="work-badge">{item.item_type_display}</span>
                                                {item.is_low_stock && <span className="work-badge work-badge--shoshilinch">Kam qoldi</span>}
                                            </span>
                                            <span className="stock-amount">{qty(item.quantity)} {item.unit}</span>
                                            <span className="work-meta">
                                                Ogohlantirish chegarasi: {qty(item.low_stock_threshold)} {item.unit}
                                            </span>
                                        </div>
                                        <div className="work-side">
                                            <button type="button" className="btn-ghost" onClick={() => quickTx(item, 'sarf')}>Sarf</button>
                                            <button type="button" className="btn-ghost" onClick={() => quickTx(item, 'kirim')}>Kirim</button>
                                            {isOwner && (
                                                <>
                                                    <button type="button" className="farm-item-action" onClick={() => handleThreshold(item)}>
                                                        Chegara
                                                    </button>
                                                    <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDeleteItem(item)}>
                                                        O'chirish
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}

                        {/* Kirim / sarf yozish */}
                        <h3 className="section-title">Kirim yoki sarf yozish</h3>
                        <div className="work-card" id="inventory-form">
                            {sortedItems.length === 0 ? (
                                <p className="empty-state">Avval omborga mahsulot qo'shilishi kerak.</p>
                            ) : (
                                <form onSubmit={handleAddTx}>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Mahsulot</label>
                                            <select name="inventory_item" value={selectedItemId} onChange={handleTxChange}>
                                                {sortedItems.map((i) => (
                                                    <option key={i.id} value={i.id}>{i.item_name} ({qty(i.quantity)} {i.unit})</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="form-field">
                                            <label>Harakat</label>
                                            <select name="transaction_type" value={txForm.transaction_type} onChange={handleTxChange}>
                                                {Object.entries(TX_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                            </select>
                                        </div>
                                    </div>
                                    <div className="form-row">
                                        <div className="form-field">
                                            <label>Miqdor{selectedItem ? ` (${selectedItem.unit})` : ''}</label>
                                            <input type="number" name="quantity" min="0.01" step="0.01" value={txForm.quantity}
                                                onChange={handleTxChange} required />
                                        </div>
                                        <div className="form-field">
                                            <label>Sana</label>
                                            <input type="date" name="date" value={txForm.date} onChange={handleTxChange} required />
                                        </div>
                                    </div>
                                    <div className="form-field">
                                        <label>Izoh (ixtiyoriy)</label>
                                        <input type="text" name="note" value={txForm.note} onChange={handleTxChange}
                                            placeholder="Masalan: ertalabki ovqatlantirish" />
                                    </div>
                                    {selectedItem && (
                                        <p className="workers-hint">Hozir omborda: {qty(selectedItem.quantity)} {selectedItem.unit}</p>
                                    )}
                                    {txError && <p className="error-text" role="alert">{txError}</p>}
                                    <button type="submit" className="btn-primary btn-auto" disabled={savingTx}>
                                        {savingTx ? 'Kuting...' : 'Yozish'}
                                    </button>
                                </form>
                            )}
                        </div>

                        {/* Yangi mahsulot (faqat fermer) */}
                        {isOwner && (
                            <>
                                <h3 className="section-title">Yangi mahsulot qo'shish</h3>
                                <div className="work-card">
                                    <form onSubmit={handleAddItem}>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>Nomi</label>
                                                <input type="text" name="item_name" value={itemForm.item_name} onChange={handleItemChange}
                                                    placeholder="Masalan: Omixta yem" required />
                                            </div>
                                            <div className="form-field">
                                                <label>Turi</label>
                                                <select name="item_type" value={itemForm.item_type} onChange={handleItemChange}>
                                                    {Object.entries(ITEM_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                                </select>
                                            </div>
                                        </div>
                                        <div className="form-row">
                                            <div className="form-field">
                                                <label>O'lchov birligi</label>
                                                <input type="text" name="unit" value={itemForm.unit} onChange={handleItemChange}
                                                    placeholder="kg, litr, dona, qop" required />
                                            </div>
                                            <div className="form-field">
                                                <label>Hozirgi miqdor</label>
                                                <input type="number" name="quantity" min="0" step="0.01" value={itemForm.quantity}
                                                    onChange={handleItemChange} required />
                                            </div>
                                        </div>
                                        <div className="form-field">
                                            <label>Kam qolish chegarasi (shundan kam qolsa ogohlantiriladi)</label>
                                            <input type="number" name="low_stock_threshold" min="0" step="0.01"
                                                value={itemForm.low_stock_threshold} onChange={handleItemChange} required />
                                        </div>
                                        {itemError && <p className="error-text" role="alert">{itemError}</p>}
                                        <button type="submit" className="btn-primary btn-auto" disabled={savingItem}>
                                            {savingItem ? 'Kuting...' : "Mahsulot qo'shish"}
                                        </button>
                                    </form>
                                </div>
                            </>
                        )}

                        {/* Tarix */}
                        <h3 className="section-title">Kirim-sarf tarixi</h3>
                        <div className="filter-bar">
                            <select value={filters.inventory_item} onChange={(e) => setFilters({ ...filters, inventory_item: e.target.value })}>
                                <option value="">Barcha mahsulotlar</option>
                                {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                            </select>
                            <select value={filters.transaction_type} onChange={(e) => setFilters({ ...filters, transaction_type: e.target.value })}>
                                <option value="">Kirim va sarf</option>
                                <option value="sarf">Faqat sarf</option>
                                <option value="kirim">Faqat kirim</option>
                            </select>
                        </div>
                        {history.length === 0 ? (
                            <p className="empty-state">Yozuvlar yo'q</p>
                        ) : (
                            <ul className="work-list">
                                {history.map((t) => (
                                    <li key={t.id} className={`work-item work-item--${t.transaction_type === 'kirim' ? 'bajarildi' : 'yangi'}`}>
                                        <div className="work-main">
                                            <span className="work-title">
                                                {t.inventory_name}:{' '}
                                                <span className={t.transaction_type === 'kirim' ? 'amount-in' : 'amount-out'}>
                                                    {t.transaction_type === 'kirim' ? '+' : '−'}{qty(t.quantity)} {t.inventory_unit}
                                                </span>
                                            </span>
                                            <span className="work-meta">
                                                {t.transaction_type_display} · {formatDate(t.date)} · Yozgan:{' '}
                                                <strong>
                                                    {t.recorded_by ? `${roleLabel(t.recorded_by)} ${t.recorded_by_name}` : "noma'lum"}
                                                </strong>
                                            </span>
                                            {t.note && <span className="work-desc">{t.note}</span>}
                                        </div>
                                        {isOwner && (
                                            <div className="work-side">
                                                <button type="button" className="farm-item-action farm-item-action--danger" onClick={() => handleDeleteTx(t)}>
                                                    O'chirish
                                                </button>
                                            </div>
                                        )}
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

export default Inventory;
