import { useEffect, useState } from 'react';
import api from '../api/axios';
import { formatMoney, today } from '../utils/format';
import { t } from '../i18n';

const asList = (data) => (Array.isArray(data) ? data : data?.results ?? []);

/**
 * "Naqd / Nasiyaga" tanlovi.
 * kind: 'mijoz' (sotilganda: kim nasiyaga oldi) yoki 'taminotchi' (xarid qilinganda: kimdan nasiyaga olindi)
 * total: jami summa (oldindan to'langan qismni tekshirish va ko'rsatish uchun)
 */
function CreditFields({ farmId, kind, total, value, onChange }) {
    const [parties, setParties] = useState([]);
    const buying = kind === 'taminotchi';

    useEffect(() => {
        if (!value.on_credit) return undefined;
        let cancelled = false;
        api.get('debt-party/', { params: { farm: farmId, kind } })
            .then((res) => !cancelled && setParties(asList(res.data)))
            .catch(() => !cancelled && setParties([]));
        return () => {
            cancelled = true;
        };
    }, [farmId, kind, value.on_credit]);

    const set = (patch) => onChange({ ...value, ...patch });
    const paid = Number(value.paid_now) || 0;
    const sum = Number(total) || 0;

    return (
        <div className="credit-box">
            <div className="credit-toggle" role="radiogroup" aria-label={t("To'lov usuli")}>
                <button type="button" role="radio" aria-checked={!value.on_credit}
                    className={`credit-opt${!value.on_credit ? ' credit-opt--on' : ''}`}
                    onClick={() => set({ on_credit: false })}>
                    {t('Naqd')}
                </button>
                <button type="button" role="radio" aria-checked={value.on_credit}
                    className={`credit-opt${value.on_credit ? ' credit-opt--on' : ''}`}
                    onClick={() => set({ on_credit: true })}>
                    {t('Nasiyaga (qarz)')}
                </button>
            </div>
            {value.on_credit && (
                <>
                    <div className="form-row">
                        <div className="form-field">
                            <label>{buying ? t('Kimdan nasiyaga olindi') : t('Kim nasiyaga oldi')}</label>
                            <select value={value.party} onChange={(e) => set({ party: e.target.value })}>
                                <option value="">{t('+ Yangi odam yozish')}</option>
                                {parties.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.name}{p.totals && Number(p.totals.remaining) > 0 ? ` (${t('qarz')}: ${formatMoney(p.totals.remaining)})` : ''}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {!value.party && (
                            <div className="form-field">
                                <label>{t('Ismi')}</label>
                                <input type="text" value={value.party_name} maxLength={120}
                                    placeholder={buying ? t("Masalan: Yem do'koni") : t('Masalan: Sutxona, Karim aka')}
                                    onChange={(e) => set({ party_name: e.target.value })} required />
                            </div>
                        )}
                    </div>
                    <div className="form-row">
                        <div className="form-field">
                            <label>{t("Qachongacha to'lanadi")}</label>
                            <input type="date" value={value.due_date} min={today()}
                                onChange={(e) => set({ due_date: e.target.value })} />
                        </div>
                        <div className="form-field">
                            <label>{t("Hozir to'langan summa (ixtiyoriy)")}</label>
                            <input type="number" min="0" step="0.01" inputMode="decimal" value={value.paid_now}
                                placeholder="0" onChange={(e) => set({ paid_now: e.target.value })} />
                        </div>
                    </div>
                    <p className="workers-hint">
                        {sum > 0
                            ? `${t('Qarz: {sum}.', { sum: formatMoney(Math.max(sum - paid, 0)) })} `
                            : ''}
                        {buying
                            ? t("Pul hozir balansdan ayrilmaydi. Qarzni to'laganingizda (Qarzlar sahifasida) shu summa chiqim bo'lib yoziladi.")
                            : t("Pul hozir balansga tushmaydi. Mijoz qarzni to'lagach (Qarzlar sahifasida) shu summa kirim bo'lib yoziladi.")}
                    </p>
                </>
            )}
        </div>
    );
}

export default CreditFields;
