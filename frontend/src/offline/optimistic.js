// Internet yo'qda qilingan o'zgarishni telefondagi nusxaga darhol qo'llaydi, shunda ekranda natija
// ko'rinadi (yangi yozuv ro'yxatda chiqadi, o'chirilgani yo'qoladi, hayvonlar soni/ombor miqdori o'zgaradi).
// Server javobi kelganda sahifalar baribir yangi ma'lumotni qayta yuklaydi, shuning uchun bu faqat vaqtinchalik ko'rinish.

import { idbAll, idbDelete, idbPut } from './idb';

const PRIORITY = { oddiy: 'Oddiy', muhim: 'Muhim', shoshilinch: 'Shoshilinch' };
const TASK_STATUS = { yangi: 'Yangi', jarayonda: 'Jarayonda', bajarildi: 'Bajarildi' };
const EVENT_TYPE = {
    kasallik: 'Kasallik', davolash: 'Davolash', vaksinatsiya: 'Vaksinatsiya',
    tugilish: "Tug'ilish", olim: "O'lim", vazn_olchash: "Vazn o'lchash",
};
const EVENT_STATUS = { boshlangan: 'Boshlangan', davom_etmoqda: 'Davom etmoqda', yakunlangan: 'Yakunlangan' };
const GROUP_STATUS = { faol: 'Faol', sotilgan: 'Sotilgan', olgan: "O'lgan", yoqolgan: "Yo'qolgan" };
const ITEM_TYPE = { ozuqa: 'Ozuqa', dori: 'Dori-darmon', boshqa: 'Boshqa' };
const MOVE_TYPE = { kirim: 'Kirim', sarf: 'Sarf' };
const SEX = { urgochi: "Urg'ochi", erkak: 'Erkak' };
const ANIMAL_STATUS = { faol: 'Faol', sotilgan: 'Sotilgan', olgan: "O'lgan" };
const SESSION = { kun: 'Butun kun', ertalab: 'Ertalab', kechqurun: 'Kechqurun' };

const COUNT_EVENTS = ['olim', 'tugilish'];

const listOf = (data) => (Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : null);
const sameId = (a, b) => a != null && b != null && String(a) === String(b);
const num = (v) => Number(v) || 0;
const money = (n) => (Math.round(n * 100) / 100).toFixed(2);
const todayStr = () => new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD, mahalliy vaqt bilan

export function currentUser() {
    try {
        return JSON.parse(localStorage.getItem('user')) || null;
    } catch {
        return null;
    }
}

/* ---------- Keshdagi yozuvlar bilan ishlash ---------- */

export async function userEntries(userId) {
    const prefix = `${userId}|`;
    return (await idbAll('cache')).filter((e) => e.key.startsWith(prefix));
}

function recordsOf(entries, resource) {
    const out = [];
    for (const e of entries) {
        if (e.path === `${resource}/`) {
            const list = listOf(e.data);
            if (list) out.push(...list);
        } else if (e.path.startsWith(`${resource}/`) && /^[a-z-]+\/-?\d+\/$/.test(e.path) && e.data && !Array.isArray(e.data)) {
            out.push(e.data);
        }
    }
    return out;
}

export function findRecord(entries, resource, id) {
    return recordsOf(entries, resource).find((r) => sameId(r.id, id)) || null;
}

function withList(data, list) {
    if (Array.isArray(data)) return list;
    const next = { ...data, results: list };
    if (typeof data.count === 'number') next.count = list.length;
    return next;
}

// Yozuv shu ro'yxat so'rovining filtriga mos keladimi (masalan ?farm=3&status=faol)
function matchesParams(rec, params = {}) {
    for (const [k, v] of Object.entries(params)) {
        if (v === '' || v == null) continue;
        if (k === 'farm' || k === 'status' || k === 'transaction_type' || k === 'category' || k === 'item_type'
            || k === 'event_type' || k === 'inventory_item' || k === 'animal' || k === 'group' || k === 'sex') {
            if (rec[k] !== undefined && String(rec[k]) !== String(v)) return false;
        } else if (k === 'open' && (v === 1 || v === '1' || v === true)) {
            if (rec.status === 'bajarildi') return false;
        } else if (k === 'low' && (v === 1 || v === '1' || v === true)) {
            if (!rec.is_low_stock) return false;
        } else if (k === 'active' && (v === 1 || v === '1' || v === true)) {
            if (rec.status === 'yakunlangan') return false;
        } else if (k === 'date_from') {
            if (rec.date && rec.date < v) return false;
        } else if (k === 'date_to') {
            if (rec.date && rec.date > v) return false;
        }
    }
    return true;
}

/* ---------- Ko'rinadigan (read-only) maydonlarni to'ldirish ---------- */

function derive(resource, rec, entries) {
    const user = currentUser();
    const out = { ...rec };

    if (resource === 'tasks') {
        out.priority_display = PRIORITY[out.priority] ?? out.priority;
        out.status_display = TASK_STATUS[out.status] ?? out.status;
        out.is_overdue = Boolean(out.due_date && out.status !== 'bajarildi' && out.due_date < todayStr());
        if (out.assigned_to) {
            const w = recordsOf(entries, 'workers').find((x) => sameId(x.user, out.assigned_to));
            out.assigned_to_name = w?.user_full_name || out.assigned_to_name || '…';
        } else {
            out.assigned_to_name = 'Barcha ishchilar';
        }
        out.created_by_name ??= user?.username ?? null;
    } else if (resource === 'animals-group') {
        const type = recordsOf(entries, 'animals-type').find((t) => sameId(t.id, out.animal_type));
        const farm = recordsOf(entries, 'farms').find((f) => sameId(f.id, out.farm));
        out.animal_type_name = type?.name ?? out.animal_type_name ?? '';
        out.farm_name = farm?.name ?? out.farm_name ?? '';
        out.status_display = GROUP_STATUS[out.status] ?? out.status;
    } else if (resource === 'animals-event') {
        const group = recordsOf(entries, 'animals-group').find((g) => sameId(g.id, out.animal_group));
        if (group) {
            out.farm = group.farm;
            out.animal_group_label = group.breed ? `${group.animal_type_name} (${group.breed})` : group.animal_type_name;
            out.animal_group_count = group.count;
        }
        out.event_type_display = EVENT_TYPE[out.event_type] ?? out.event_type;
        out.status_display = EVENT_STATUS[out.status] ?? out.status;
        const end = out.end_date ? new Date(out.end_date) : new Date();
        out.days_since_start = out.start_date ? Math.max(0, Math.floor((end - new Date(out.start_date)) / 86400000)) : 0;
        out.recorded_by_username ??= user?.username ?? null;
        out.recorded_by_name ??= user?.username ?? null;
    } else if (resource === 'animals-card') {
        const group = recordsOf(entries, 'animals-group').find((g) => sameId(g.id, out.group));
        if (group) {
            out.farm = group.farm;
            out.group_label = group.breed ? `${group.animal_type_name} (${group.breed})` : group.animal_type_name;
        }
        out.sex_display = SEX[out.sex] ?? out.sex;
        out.status_display = ANIMAL_STATUS[out.status] ?? out.status;
    } else if (resource === 'animals-weight' || resource === 'animals-milk') {
        const animal = recordsOf(entries, 'animals-card').find((a) => sameId(a.id, out.animal));
        if (animal) {
            out.farm = animal.farm;
            out.animal_tag = animal.tag_number;
        }
        if (resource === 'animals-milk') out.session_display = SESSION[out.session] ?? out.session;
        out.recorded_by_name ??= user?.username ?? null;
    } else if (resource === 'inventory-item') {
        out.item_type_display = ITEM_TYPE[out.item_type] ?? out.item_type;
        out.quantity = money(num(out.quantity));
        out.low_stock_threshold = money(num(out.low_stock_threshold));
        out.is_low_stock = num(out.quantity) <= num(out.low_stock_threshold);
        const farm = recordsOf(entries, 'farms').find((f) => sameId(f.id, out.farm));
        out.farm_name = farm?.name ?? out.farm_name ?? '';
    } else if (resource === 'inventory-transaction') {
        const item = recordsOf(entries, 'inventory-item').find((i) => sameId(i.id, out.inventory_item));
        if (item) {
            out.farm = item.farm;
            out.inventory_name = item.item_name;
            out.inventory_unit = item.unit;
        }
        out.transaction_type_display = MOVE_TYPE[out.transaction_type] ?? out.transaction_type;
        out.recorded_by_name ??= user?.username ?? null;
    } else if (resource === 'finance') {
        const farm = recordsOf(entries, 'farms').find((f) => sameId(f.id, out.farm));
        const group = recordsOf(entries, 'animals-group').find((g) => sameId(g.id, out.animal_group));
        out.farm_name = farm?.name ?? out.farm_name ?? '';
        if (group) {
            out.animal_group_label = group.breed ? `${group.animal_type_name} (${group.breed})` : group.animal_type_name;
            out.animal_group_info = `${group.animal_type_name} - ${group.count} ta (${group.farm_name})`;
        }
        out.recorded_by_username ??= user?.username ?? null;
    } else if (resource === 'farms') {
        out.owner_username ??= user?.username ?? null;
        out.can_view_finance ??= true;
    }
    return out;
}

/* ---------- Yon ta'sirlar (hayvonlar soni, ombor miqdori) ---------- */

function adjustGroup(entries, groupId, delta) {
    return patchRecord(entries, 'animals-group', groupId, (g) => {
        const count = Math.max(0, num(g.count) + delta);
        let status = g.status;
        if (count === 0 && g.status === 'faol') status = 'olgan';
        else if (count > 0 && (g.status === 'olgan' || g.status === 'sotilgan')) status = 'faol';
        return { ...g, count, status, status_display: GROUP_STATUS[status] ?? status };
    });
}

function adjustItem(entries, itemId, delta) {
    return patchRecord(entries, 'inventory-item', itemId, (i) => {
        const quantity = Math.max(0, num(i.quantity) + delta);
        return { ...i, quantity: money(quantity), is_low_stock: quantity <= num(i.low_stock_threshold) };
    });
}

// Keshdagi (ro'yxat va alohida) yozuvlarni o'zgartiradi. Natija entries ichiga yoziladi (xotirada), saqlash alohida.
function patchRecord(entries, resource, id, fn) {
    for (const e of entries) {
        if (e.path === `${resource}/`) {
            const list = listOf(e.data);
            if (list?.some((r) => sameId(r.id, id))) {
                e.data = withList(e.data, list.map((r) => (sameId(r.id, id) ? fn(r) : r)));
                e._dirty = true;
            }
        } else if (e.path === `${resource}/${id}/` && e.data && !Array.isArray(e.data)) {
            e.data = fn(e.data);
            e._dirty = true;
        }
    }
}

async function flush(entries) {
    for (const e of entries) {
        if (e._delete) {
            await idbDelete('cache', e.key);
        } else if (e._dirty) {
            const { _dirty, ...clean } = e;
            await idbPut('cache', clean);
            delete e._dirty;
        }
    }
}

export class LocalValidationError extends Error {
    constructor(field, message) {
        super(message);
        this.field = field;
        this.data = { [field]: [message] };
    }
}

/* ---------- Asosiy funksiyalar ---------- */

// Yangi yozuv: ro'yxatlarga qo'shadi va ko'rinadigan yozuvni qaytaradi
export async function applyCreate(userId, resource, payload, tmpId) {
    const entries = await userEntries(userId);
    const user = currentUser();
    let rec = { ...payload, id: tmpId, _pending: true, created_at: new Date().toISOString() };

    if (resource === 'inventory-transaction') {
        const item = findRecord(entries, 'inventory-item', payload.inventory_item);
        const q = num(payload.quantity);
        if (payload.transaction_type === 'sarf' && item && q > num(item.quantity)) {
            throw new LocalValidationError('quantity', `Omborda yetarli emas. Hozir: ${num(item.quantity)} ${item.unit}`);
        }
        rec.recorded_by = user?.id ?? null;
    }
    if (resource === 'animals-event') {
        const group = findRecord(entries, 'animals-group', payload.animal_group);
        if (COUNT_EVENTS.includes(payload.event_type)) {
            rec.status = 'yakunlangan';
            rec.end_date = payload.end_date || payload.start_date;
            if (payload.event_type === 'olim' && group && num(payload.animal_count) > num(group.count)) {
                throw new LocalValidationError('animal_count', `Guruhda faqat ${group.count} ta hayvon bor`);
            }
        } else {
            rec.status ??= 'boshlangan';
        }
        rec.recorded_by = user?.id ?? null;
    }
    if (resource === 'animals-group') {
        rec.status ??= 'faol';
        rec.updated_at = rec.created_at;
    }
    if (resource === 'animals-card') {
        rec.status ??= 'faol';
        rec.sex ??= 'urgochi';
        rec.updated_at = rec.created_at;
    }
    if (resource === 'animals-weight' || resource === 'animals-milk') {
        rec.recorded_by = user?.id ?? null;
        if (resource === 'animals-milk') rec.session ??= 'kun';
    }
    if (resource === 'tasks') {
        rec.status ??= 'yangi';
        rec.priority ??= 'oddiy';
        rec.created_by = user?.id ?? null;
    }
    if (resource === 'farms') rec.owner = user?.id ?? null;
    if (resource === 'inventory-item') rec.quantity ??= '0';
    if (resource === 'finance') {
        rec.recorded_by = user?.id ?? null;
        if (!(num(payload.amount) > 0)) throw new LocalValidationError('amount', "Summa 0 dan katta bo'lishi kerak");
    }
    rec = derive(resource, rec, entries);

    // Yon ta'sirlar
    if (resource === 'inventory-transaction') {
        adjustItem(entries, payload.inventory_item, (payload.transaction_type === 'sarf' ? -1 : 1) * num(payload.quantity));
    } else if (resource === 'animals-event' && COUNT_EVENTS.includes(payload.event_type)) {
        adjustGroup(entries, payload.animal_group, (payload.event_type === 'olim' ? -1 : 1) * num(payload.animal_count));
    } else if (resource === 'finance' && payload.animal_count && payload.animal_group) {
        adjustGroup(entries, payload.animal_group, -num(payload.animal_count));
    }

    for (const e of entries) {
        if (e.path !== `${resource}/`) continue;
        const list = listOf(e.data);
        if (!list || !matchesParams(rec, e.params)) continue;
        e.data = withList(e.data, [rec, ...list]);
        e._dirty = true;
    }
    await flush(entries);
    return rec;
}

// Mavjud yozuvni o'zgartirish (PATCH): natijadagi yozuvni qaytaradi
export async function applyUpdate(userId, resource, id, patch) {
    const entries = await userEntries(userId);
    const current = findRecord(entries, resource, id);
    let merged = null;
    patchRecord(entries, resource, id, (r) => {
        merged = derive(resource, { ...r, ...patch, _pending: true }, entries);
        return merged;
    });
    await flush(entries);
    return merged ?? { ...(current || {}), ...patch, id };
}

// Yozuvni o'chirish (DELETE): hayvon soni/ombor miqdoridagi ta'sirni qaytaradi
export async function applyDelete(userId, resource, id) {
    const entries = await userEntries(userId);
    const rec = findRecord(entries, resource, id);

    if (rec && resource === 'inventory-transaction') {
        adjustItem(entries, rec.inventory_item, (rec.transaction_type === 'sarf' ? 1 : -1) * num(rec.quantity));
    } else if (rec && resource === 'animals-event' && COUNT_EVENTS.includes(rec.event_type) && rec.animal_count) {
        adjustGroup(entries, rec.animal_group, (rec.event_type === 'olim' ? 1 : -1) * num(rec.animal_count));
    } else if (rec && resource === 'finance' && rec.animal_count && rec.animal_group) {
        adjustGroup(entries, rec.animal_group, num(rec.animal_count));
    }

    for (const e of entries) {
        if (e.path === `${resource}/${id}/`) {
            e._delete = true;
        } else if (e.path === `${resource}/`) {
            const list = listOf(e.data);
            if (list?.some((r) => sameId(r.id, id))) {
                e.data = withList(e.data, list.filter((r) => !sameId(r.id, id)));
                e._dirty = true;
            }
        }
    }
    await flush(entries);
}
