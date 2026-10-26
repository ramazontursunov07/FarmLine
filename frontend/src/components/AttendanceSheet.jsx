import { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import { formatMoney } from '../utils/format';

const asList = (d) => (Array.isArray(d) ? d : d?.results ?? []);
const pad = (n) => String(n).padStart(2, '0');
const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const monthKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
const NEXT = { keldi: 'kelmadi', kelmadi: 'ruxsat', ruxsat: 'keldi' };

function AttendanceSheet({ workers }) {
    const [month, setMonth] = useState(() => monthKey(new Date()));
    const [records, setRecords] = useState({}); // `${worker}-${date}` -> status
    const [error, setError] = useState('');
    const [todayStr] = useState(() => dayKey(new Date()));

    const [year, mon] = month.split('-').map(Number);
    const daysInMonth = new Date(year, mon, 0).getDate();

    const load = useCallback(async () => {
        try {
            const farmId = workers[0]?.farm;
            if (!farmId) return;
            const { data } = await api.get('attendance/', { params: { farm: farmId, month } });
            const map = {};
            asList(data).forEach((r) => { map[`${r.worker}-${r.date}`] = r.status; });
            setRecords(map);
            setError('');
        } catch (err) {
            setError(getErrorMessage(err, "Davomatni yuklab bo'lmadi"));
        }
    }, [workers, month]);

    useEffect(() => {
        load();
    }, [load]);

    const shift = (delta) => {
        const d = new Date(year, mon - 1 + delta, 1);
        setMonth(monthKey(d));
    };

    const toggle = async (worker, dateStr) => {
        const key = `${worker.id}-${dateStr}`;
        const current = records[key] || 'keldi';
        const next = NEXT[current];
        const prev = records;
        setRecords({ ...records, [key]: next === 'keldi' ? undefined : next });
        try {
            await api.post('attendance/', { worker: worker.id, date: dateStr, status: next });
            setError('');
        } catch (err) {
            setRecords(prev);
            setError(getErrorMessage(err, "Belgilab bo'lmadi"));
        }
    };

    const stats = useMemo(() => {
        const out = {};
        workers.forEach((w) => {
            let absent = 0;
            let excused = 0;
            for (let d = 1; d <= daysInMonth; d += 1) {
                const s = records[`${w.id}-${year}-${pad(mon)}-${pad(d)}`];
                if (s === 'kelmadi') absent += 1;
                else if (s === 'ruxsat') excused += 1;
            }
            const deduction = Math.round((Number(w.monthly_salary) * absent) / daysInMonth);
            out[w.id] = { absent, excused, deduction };
        });
        return out;
    }, [records, workers, daysInMonth, year, mon]);

    if (workers.length === 0) return null;

    return (
        <details className="more-menu attendance">
            <summary className="section-title">📅 Davomat</summary>
            <p className="workers-hint">
                Faqat kelmagan kunlarni belgilang: kunni bossangiz <b>✗ kelmadi</b>, yana bossangiz <b>ruxsat</b>, yana bossangiz
                oddiy holatga qaytadi. Belgilanmagan kun — keldi. «Kelmadi» kunlari oy oxirida oylikdan ushlab qolinadi,
                «ruxsat» ushlanmaydi.
            </p>
            <div className="attendance-month">
                <button type="button" className="btn-ghost" onClick={() => shift(-1)}>←</button>
                <strong>{pad(mon)}.{year}</strong>
                <button type="button" className="btn-ghost" onClick={() => shift(1)}>→</button>
            </div>
            {error && <p className="error-text" role="alert">{error}</p>}
            {workers.map((w) => {
                const st = stats[w.id];
                return (
                    <div key={w.id} className="attendance-card">
                        <div className="attendance-head">
                            <strong>{w.user_full_name}</strong>
                            <span className="worker-meta">
                                Kelmagan: {st.absent} kun
                                {st.excused > 0 && ` · ruxsat: ${st.excused}`}
                                {st.deduction > 0 && ` · ushlanadi ≈ ${formatMoney(st.deduction)}`}
                            </span>
                        </div>
                        <div className="attendance-days">
                            {Array.from({ length: daysInMonth }, (_, i) => {
                                const day = i + 1;
                                const dateStr = `${year}-${pad(mon)}-${pad(day)}`;
                                const s = records[`${w.id}-${dateStr}`];
                                const future = dateStr > todayStr;
                                return (
                                    <button key={day} type="button" disabled={future}
                                        className={`att-day${s ? ` att-day--${s}` : ''}`}
                                        aria-label={`${day}-kun: ${s === 'kelmadi' ? 'kelmadi' : s === 'ruxsat' ? 'ruxsat bilan' : 'keldi'}`}
                                        onClick={() => toggle(w, dateStr)}>
                                        {day}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                );
            })}
        </details>
    );
}

export default AttendanceSheet;
