import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/axios';
import './NotificationBell.css';

const POLL_MS = 60000;

const ICONS = {
    calving: '🐄', dry_off: '🥛', rebreed: '🐄', debt: '💸', withdrawal: '⛔',
    vaccination: '💉', feed: '🌾', spending: '📈', event: '🔔', milk_drop: '📉',
};

function BellIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 01-3.4 0" />
        </svg>
    );
}

function timeAgo(iso) {
    const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return 'hozir';
    if (mins < 60) return `${mins} daqiqa oldin`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} soat oldin`;
    return `${Math.floor(hours / 24)} kun oldin`;
}

// Navbardagi qo'ng'iroqcha: o'qilmaganlar soni va bildirishnomalar ro'yxati
export default function NotificationBell() {
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const [unread, setUnread] = useState(0);
    const [items, setItems] = useState(null);
    const [error, setError] = useState(false);
    const box = useRef(null);

    const loadCount = useCallback(async () => {
        try {
            const { data } = await api.get('notifications/count/');
            setUnread(data.unread_count);
        } catch {
            /* offline yoki server javob bermadi: qo'ng'iroqcha jimgina eski sonni ko'rsatadi */
        }
    }, []);

    const loadList = useCallback(async () => {
        try {
            const { data } = await api.get('notifications/');
            setItems(data.results);
            setUnread(data.unread_count);
            setError(false);
        } catch {
            setError(true);
        }
    }, []);

    useEffect(() => {
        loadCount();
        const timer = setInterval(() => { if (!document.hidden) loadCount(); }, POLL_MS);
        const onVisible = () => { if (!document.hidden) loadCount(); };
        document.addEventListener('visibilitychange', onVisible);
        return () => { clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
    }, [loadCount]);

    useEffect(() => {
        if (!open) return undefined;
        loadList();
        const onDown = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', onDown);
        document.addEventListener('keydown', onKey);
        return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
    }, [open, loadList]);

    const markRead = async (payload) => {
        try {
            const { data } = await api.post('notifications/read/', payload);
            setUnread(data.unread_count);
            return true;
        } catch {
            return false;
        }
    };

    const handleOpenItem = async (n) => {
        if (!n.is_read && await markRead({ ids: [n.id] })) {
            setItems((list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
        }
        if (n.link) {
            setOpen(false);
            navigate(n.link);
        }
    };

    const handleReadAll = async () => {
        if (await markRead({ all: true })) setItems((list) => list.map((x) => ({ ...x, is_read: true })));
    };

    const handleClear = async () => {
        try {
            const { data } = await api.post('notifications/clear/');
            setUnread(data.unread_count);
            setItems((list) => list.filter((x) => !x.is_read));
        } catch {
            setError(true);
        }
    };

    return (
        <div className="notif" ref={box}>
            <button type="button" className="notif-btn" onClick={() => setOpen((v) => !v)}
                aria-label={unread ? `Bildirishnomalar, ${unread} ta yangi` : 'Bildirishnomalar'}
                aria-expanded={open} aria-haspopup="true">
                <BellIcon />
                {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
            </button>
            {open && (
                <div className="notif-panel" role="region" aria-label="Bildirishnomalar">
                    <div className="notif-head">
                        <strong>Bildirishnomalar</strong>
                        <div className="notif-actions">
                            {unread > 0 && <button type="button" className="notif-link" onClick={handleReadAll}>Hammasini o'qildi</button>}
                            {items && items.some((n) => n.is_read) && (
                                <button type="button" className="notif-link" onClick={handleClear}>Tozalash</button>
                            )}
                        </div>
                    </div>
                    {error && <p className="notif-empty">Yuklab bo'lmadi. Internetni tekshiring.</p>}
                    {!error && items === null && <p className="notif-empty">Yuklanmoqda...</p>}
                    {!error && items && items.length === 0 && <p className="notif-empty">Hozircha bildirishnoma yo'q.</p>}
                    {items && items.length > 0 && (
                        <ul className="notif-list">
                            {items.map((n) => (
                                <li key={n.id}>
                                    <button type="button" className={`notif-item${n.is_read ? '' : ' notif-item--new'}`}
                                        onClick={() => handleOpenItem(n)}>
                                        <span className="notif-icon" aria-hidden="true">{ICONS[n.kind] || ICONS.event}</span>
                                        <span className="notif-text">
                                            <span className="notif-title">{n.title}</span>
                                            {n.body && <span className="notif-body">{n.body}</span>}
                                            <span className="notif-time">{timeAgo(n.created_at)}</span>
                                        </span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
