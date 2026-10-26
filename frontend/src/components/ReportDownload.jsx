import { useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { today } from '../utils/format';

const FILES = [
    ['xlsx', 'Excel yuklab olish'],
    ['pdf', 'PDF yuklab olish'],
];

// Server xatosi blob ko'rinishida keladi (responseType: 'blob'): avval matnga o'giramiz
async function readError(err) {
    const data = err.response?.data;
    if (data instanceof Blob) {
        try {
            err.response.data = JSON.parse(await data.text());
        } catch {
            err.response.data = null;
        }
    }
    return getErrorMessage(err, "Hisobotni yuklab bo'lmadi");
}

// Tanlangan oy uchun kirim-chiqim, foyda/zarar va ombor hisobotini Excel yoki PDF qilib yuklab beradi.
function ReportDownload({ farmId }) {
    const currentMonth = today().slice(0, 7); // YYYY-MM
    const [month, setMonth] = useState(currentMonth);
    const [busy, setBusy] = useState('');
    const [error, setError] = useState('');

    const download = async (file) => {
        if (!/^\d{4}-\d{2}$/.test(month)) {
            setError("Oyni tanlang (masalan, 2026-10)");
            return;
        }
        setError('');
        setBusy(file);
        try {
            const { data } = await api.get('finance/export/', {
                params: { farm: farmId, month, file },
                responseType: 'blob',
                timeout: 60000, // PDF yasash oddiy so'rovdan sekinroq
            });
            const url = URL.createObjectURL(data);
            const link = document.createElement('a');
            link.href = url;
            link.download = `farmline-${month}.${file}`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) {
            setError(await readError(err));
        } finally {
            setBusy('');
        }
    };

    return (
        <>
            <h3 className="section-title">Hisobotni yuklab olish</h3>
            <p className="workers-hint">
                Tanlangan oy bo'yicha kirim, chiqim, foyda/zarar, sut (sog'ilgan, sotilgan, tannarx) va ombor holati. Bank yoki shirkatga ko'rsatish uchun qulay.
            </p>
            <div className="filter-bar">
                <input
                    type="month"
                    value={month}
                    max={currentMonth}
                    onChange={(e) => {
                        setMonth(e.target.value);
                        setError('');
                    }}
                    aria-label="Hisobot oyi"
                    pattern="\d{4}-\d{2}"
                    placeholder="YYYY-MM"
                />
                {FILES.map(([file, label]) => (
                    <button key={file} type="button" className="btn-ghost" disabled={Boolean(busy)}
                        onClick={() => download(file)}>
                        {busy === file ? 'Tayyorlanmoqda...' : label}
                    </button>
                ))}
            </div>
            {error && <p className="error-text" role="alert">{error}</p>}
        </>
    );
}

export default ReportDownload;
