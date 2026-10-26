import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import QrImage from '../components/QrImage';
import './AnimalQrSheet.css';

const asList = (d) => (Array.isArray(d) ? d : d?.results ?? []);

// Hamma faol hayvonlar uchun QR bilkalar: chop etib, quloq yoki bo'yin bilkasiga yopishtiriladi.
// Telefon kamerasi bilan skanerlansa, shu hayvonning kartochkasi ochiladi.
function AnimalQrSheet() {
    const { farmId } = useParams();
    const [farm, setFarm] = useState(null);
    const [animals, setAnimals] = useState([]);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        Promise.all([api.get(`farms/${farmId}/`), api.get('animals-card/', { params: { farm: farmId } })])
            .then(([f, a]) => {
                if (cancelled) return;
                setFarm(f.data);
                setAnimals(asList(a.data).filter((x) => x.status === 'faol'));
            })
            .catch((err) => { if (!cancelled) setError(getErrorMessage(err, "Yuklab bo'lmadi")); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [farmId]);

    return (
        <div className="qr-sheet-page">
            <div className="qr-sheet-bar">
                <Link to={`/farms/${farmId}/animals`} className="back-link">← Kartochkalarga qaytish</Link>
                <button type="button" className="btn-primary btn-auto" onClick={() => window.print()}
                    disabled={animals.length === 0}>
                    🖨 Chop etish
                </button>
            </div>
            <h2 className="panel-title qr-sheet-title">{farm ? `${farm.name}: QR bilkalar` : 'QR bilkalar'}</h2>
            <p className="panel-subtitle qr-sheet-hint">
                Qog'ozga chop eting, kesib, hayvon bilkasiga yoki yem idishiga yopishtiring. Telefon kamerasi bilan
                skanerlasangiz, hayvon kartochkasi ochiladi (avval tizimga kirgan bo'lishingiz kerak).
            </p>
            {loading && <p className="empty-state">Yuklanmoqda...</p>}
            {error && <p className="error-text">{error}</p>}
            {!loading && !error && animals.length === 0 && <p className="empty-state">Faol hayvon kartochkasi yo'q</p>}
            <div className="qr-grid">
                {animals.map((a) => (
                    <div key={a.id} className="qr-label">
                        <QrImage value={`${window.location.origin}/farms/${farmId}/animals/${a.id}`} size={120}
                            alt={`№${a.tag_number} QR kodi`} />
                        <strong>№{a.tag_number}</strong>
                        {a.name && <span>{a.name}</span>}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default AnimalQrSheet;
