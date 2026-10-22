import { today } from './format';

function addDays(iso, days) {
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(y, m - 1, d + days);
    const pad = (x) => String(x).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
}

export const EMPTY_CREDIT = () => ({
    on_credit: false,
    party: '',
    party_name: '',
    due_date: addDays(today(), 7),
    paid_now: '',
});

// Yuboriladigan maydonlar: nasiya bo'lmasa, hech narsa qo'shilmaydi (eski xatti-harakat saqlanadi)
export function creditPayload(credit) {
    if (!credit.on_credit) return {};
    const out = { on_credit: true, due_date: credit.due_date || undefined };
    if (credit.party) out.party = Number(credit.party);
    else out.party_name = credit.party_name.trim();
    if (credit.paid_now !== '') out.paid_now = credit.paid_now;
    return out;
}
