import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

// Berilgan manzilni QR kod rasmiga aylantiradi (telefon kamerasi bilan skanerlanadi).
function QrImage({ value, size = 200, alt = 'QR kod' }) {
    const [src, setSrc] = useState('');

    useEffect(() => {
        let cancelled = false;
        QRCode.toDataURL(value, { width: size * 2, margin: 1, errorCorrectionLevel: 'M' })
            .then((url) => { if (!cancelled) setSrc(url); })
            .catch(() => { if (!cancelled) setSrc(''); });
        return () => { cancelled = true; };
    }, [value, size]);

    if (!src) return <div className="qr-placeholder" style={{ width: size, height: size }} />;
    return <img src={src} alt={alt} width={size} height={size} className="qr-image" />;
}

export default QrImage;
