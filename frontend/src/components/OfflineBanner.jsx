import { useState } from 'react';
import { describeOp, discardFailed, syncNow } from '../offline';
import { useOfflineState } from '../offline/state';
import { useAuth } from '../context/AuthContext';

const BAR = {
    position: 'fixed',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 1000,
    padding: '10px 16px calc(10px + env(safe-area-inset-bottom))',
    fontSize: 14,
    lineHeight: 1.4,
    color: '#fff',
    boxShadow: '0 -2px 10px rgba(0,0,0,0.15)',
};
const BTN = {
    marginLeft: 10,
    padding: '4px 10px',
    borderRadius: 6,
    border: '1px solid rgba(255,255,255,0.7)',
    background: 'transparent',
    color: '#fff',
    fontSize: 13,
    cursor: 'pointer',
};

// Internet holati va yuborilmagan o'zgarishlarni ko'rsatadigan panel (faqat tizimga kirgan foydalanuvchiga)
function OfflineBanner() {
    const { user } = useAuth();
    const { offline, pending, failed, syncing } = useOfflineState();
    const [showFailed, setShowFailed] = useState(true);

    if (!user) return null;
    if (!offline && pending === 0 && failed.length === 0 && !syncing) return null;

    let text = null;
    let color = '#3D5C45';
    if (offline) {
        color = '#8A5A00';
        text = pending > 0
            ? `Internet yo'q. ${pending} ta o'zgarish telefonda saqlandi, internet kelganda o'zi yuboriladi.`
            : "Internet yo'q. Telefondagi saqlangan ma'lumotlar ko'rsatilmoqda.";
    } else if (syncing) {
        text = "O'zgarishlar serverga yuborilmoqda…";
    } else if (pending > 0) {
        text = `${pending} ta o'zgarish hali yuborilmagan.`;
    }

    return (
        <>
            {text && (
                <div style={{ ...BAR, background: color }} role="status">
                    {text}
                    {!offline && !syncing && pending > 0 && (
                        <button type="button" style={BTN} onClick={syncNow}>Hozir yuborish</button>
                    )}
                </div>
            )}
            {failed.length > 0 && (
                <div
                    style={{ ...BAR, background: '#B3432F', bottom: text ? 'calc(44px + env(safe-area-inset-bottom))' : 0 }}
                    role="alert"
                >
                    <strong>{failed.length} ta o'zgarishni server qabul qilmadi.</strong>
                    <button type="button" style={BTN} onClick={() => setShowFailed((v) => !v)}>
                        {showFailed ? 'Yashirish' : "Ko'rish"}
                    </button>
                    {showFailed && (
                        <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                            {failed.map((op) => (
                                <li key={op.seq} style={{ marginBottom: 4 }}>
                                    {describeOp(op)} — {op.message}
                                    <button type="button" style={BTN} onClick={() => discardFailed(op.seq)}>Olib tashlash</button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </>
    );
}

export default OfflineBanner;
