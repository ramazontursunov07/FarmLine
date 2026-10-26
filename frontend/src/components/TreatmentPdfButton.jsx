import { useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

// Davolash va vaksinatsiya tarixini PDF qilib yuklaydi (butun ferma yoki bitta hayvon uchun).
function TreatmentPdfButton({ farmId, animalId, label = '📄 Davolash tarixi (PDF)', className = 'btn-ghost' }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const download = async () => {
        setBusy(true);
        setError('');
        try {
            const { data } = await api.get('animals-event/history-pdf/', {
                params: { farm: farmId, ...(animalId ? { animal: animalId } : {}) },
                responseType: 'blob',
                timeout: 60000,
            });
            const url = URL.createObjectURL(data);
            const link = document.createElement('a');
            link.href = url;
            link.download = animalId ? `davolash-${animalId}.pdf` : `davolash-tarixi-${farmId}.pdf`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) {
            setError(getErrorMessage(err, "PDF ni yuklab bo'lmadi"));
        } finally {
            setBusy(false);
        }
    };

    return (
        <>
            <button type="button" className={className} disabled={busy} onClick={download}>
                {busy ? 'Tayyorlanmoqda...' : label}
            </button>
            {error && <span className="error-text" role="alert"> {error}</span>}
        </>
    );
}

export default TreatmentPdfButton;
