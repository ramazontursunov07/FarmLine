import { useEffect, useRef, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import './AssistantChat.css';

const GREETING =
    "Salom! Men FarmLine yordamchisiman. Savol bering yoki ayting, men yozib qo'yaman: " +
    "«ombordan 50 kg yem chiqar», «bugun 200 000 so'm yem uchun chiqim yoz». Yozishdan oldin sizdan tasdiq so'rayman.";
const MAX_LEN = 1000; // backend ham shu chegarani tekshiradi
const HISTORY_LIMIT = 10; // AI ga oxirgi nechta xabar yuboriladi
const AI_TIMEOUT_MS = 60000; // AI javobi oddiy so'rovdan sekinroq bo'lishi mumkin
const VOICE_LANG = 'uz-UZ';

// Brauzer ovozni matnga o'girishni qo'llab-quvvatlasa (Chrome, Edge, Android), mikrofon tugmasi chiqadi
const SpeechRecognition =
    typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

const VOICE_ERRORS = {
    'not-allowed': "Mikrofonga ruxsat berilmagan. Brauzer sozlamalaridan ruxsat bering.",
    'service-not-allowed': "Mikrofonga ruxsat berilmagan. Brauzer sozlamalaridan ruxsat bering.",
    network: "Ovozni tanish uchun internet kerak.",
    'audio-capture': "Mikrofon topilmadi.",
    'language-not-supported': "Bu brauzer o'zbek tilidagi ovozni tanimaydi. Yozib yuboring.",
};

// Ekranning pastki o'ng burchagidagi "AI bilan suhbat" tugmasi va chat oynasi.
// onActionDone -- AI taklif qilgan amal bajarilgach chaqiriladi (sahifa ma'lumotini yangilash uchun).
function AssistantChat({ onActionDone }) {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([]); // { role: 'user' | 'assistant', content, error? }
    const [text, setText] = useState('');
    const [busy, setBusy] = useState(false);
    const [card, setCard] = useState(null); // AI taklif qilgan, tasdiq kutayotgan amal: { id, items: [{ title, details }] }
    const [confirming, setConfirming] = useState(false);
    const [listening, setListening] = useState(false);
    const [voiceError, setVoiceError] = useState('');
    const endRef = useRef(null);
    const inputRef = useRef(null);
    const recRef = useRef(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, busy, open, card]);

    useEffect(() => {
        if (open) inputRef.current?.focus();
    }, [open]);

    // Oyna yopilsa yoki sahifa almashsa, mikrofon o'chadi
    useEffect(() => () => recRef.current?.abort(), []);

    const stopListening = () => {
        recRef.current?.stop();
    };

    const toggleListening = () => {
        if (listening) {
            stopListening();
            return;
        }
        setVoiceError('');
        const rec = new SpeechRecognition();
        rec.lang = VOICE_LANG;
        rec.interimResults = true;
        rec.continuous = false;
        const base = text.trim() ? `${text.trim()} ` : '';
        rec.onresult = (e) => {
            const spoken = Array.from(e.results).map((r) => r[0].transcript).join(' ');
            setText((base + spoken).slice(0, MAX_LEN));
        };
        rec.onerror = (e) => {
            // "no-speech" -- hech narsa aytilmadi, xabar kerak emas
            if (e.error && e.error !== 'no-speech' && e.error !== 'aborted') {
                setVoiceError(VOICE_ERRORS[e.error] || "Ovozni tanib bo'lmadi. Yozib yuboring.");
            }
        };
        rec.onend = () => {
            setListening(false);
            recRef.current = null;
            inputRef.current?.focus();
        };
        recRef.current = rec;
        try {
            rec.start();
            setListening(true);
        } catch {
            setListening(false);
        }
    };

    // Eski taklif serverda ham bekor bo'ladi (javob kutilmaydi; xato bo'lsa ham zarar yo'q)
    const dropCard = () => {
        if (!card) return;
        api.post(`assistant/actions/${card.id}/cancel/`).catch(() => {});
        setCard(null);
    };

    const addAssistant = (content, error = false) =>
        setMessages((prev) => [...prev, { role: 'assistant', content, ...(error ? { error: true } : {}) }]);

    const send = async () => {
        const question = text.trim();
        if (!question || busy || confirming) return;
        stopListening();
        dropCard();
        setVoiceError('');

        // Xato bilan tugagan javoblar AI ga yuborilmaydi
        const history = messages
            .filter((m) => !m.error)
            .slice(-HISTORY_LIMIT)
            .map(({ role, content }) => ({ role, content }));

        setMessages((prev) => [...prev, { role: 'user', content: question }]);
        setText('');
        setBusy(true);

        try {
            const { data } = await api.post(
                'assistant/chat/',
                { message: question, history },
                { timeout: AI_TIMEOUT_MS }
            );
            addAssistant(data.answer);
            setCard(data.action || null);
        } catch (err) {
            addAssistant(getErrorMessage(err, "AI javob bera olmadi, birozdan keyin qayta urinib ko'ring."), true);
        } finally {
            setBusy(false);
        }
    };

    const confirmAction = async () => {
        if (!card || confirming) return;
        setConfirming(true);
        try {
            const { data } = await api.post(`assistant/actions/${card.id}/confirm/`);
            addAssistant((data.results || [data.detail]).join('\n'));
            setCard(null);
            onActionDone?.();
        } catch (err) {
            addAssistant(getErrorMessage(err, "Amalni bajarib bo'lmadi."), true);
            // Internet uzilgan bo'lsa, karta qoladi: qayta bosish mumkin. Boshqa xatoda taklif eskirgan.
            if (err.response) setCard(null);
        } finally {
            setConfirming(false);
        }
    };

    const cancelAction = () => {
        dropCard();
        addAssistant("Bekor qilindi. Hech narsa yozilmadi.");
    };

    const clearAll = () => {
        dropCard();
        setMessages([]);
    };

    const handleKeyDown = (e) => {
        // Enter - yuborish, Shift+Enter - yangi qator
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
        }
    };

    return (
        <>
            {!open && (
                <button
                    type="button"
                    className="ai-fab"
                    onClick={() => setOpen(true)}
                    aria-label="AI yordamchi bilan suhbat"
                >
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
                        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z" />
                    </svg>
                    <span>AI yordamchi</span>
                </button>
            )}

            {open && (
                <section className="ai-panel" role="dialog" aria-label="AI yordamchi">
                    <header className="ai-panel-header">
                        <h3>AI yordamchi</h3>
                        <div className="ai-panel-actions">
                            {messages.length > 0 && (
                                <button type="button" className="ai-link-btn" onClick={clearAll}
                                    disabled={busy || confirming}>
                                    Tozalash
                                </button>
                            )}
                            <button type="button" className="ai-close"
                                onClick={() => { stopListening(); setOpen(false); }}
                                aria-label="Yopish">
                                ×
                            </button>
                        </div>
                    </header>

                    <div className="ai-messages" aria-live="polite">
                        <div className="ai-msg ai-msg--assistant">{GREETING}</div>
                        {messages.map((m, i) => (
                            <div
                                key={i}
                                className={`ai-msg ai-msg--${m.role}${m.error ? ' ai-msg--error' : ''}`}
                            >
                                {m.content}
                            </div>
                        ))}
                        {busy && (
                            <div className="ai-msg ai-msg--assistant ai-typing" aria-label="Javob yozilmoqda">
                                <span /><span /><span />
                            </div>
                        )}
                        {card && (
                            <div className="ai-action" role="group" aria-label="Amalni tasdiqlash">
                                {card.items.map((item, i) => (
                                    <div key={i} className="ai-action-item">
                                        <strong>{item.title}</strong>
                                        <ul>
                                            {item.details.map((d, j) => <li key={j}>{d}</li>)}
                                        </ul>
                                    </div>
                                ))}
                                <div className="ai-action-buttons">
                                    <button type="button" className="ai-confirm" onClick={confirmAction}
                                        disabled={confirming}>
                                        {confirming ? 'Yozilmoqda...' : 'Tasdiqlash'}
                                    </button>
                                    <button type="button" className="ai-cancel" onClick={cancelAction}
                                        disabled={confirming}>
                                        Bekor qilish
                                    </button>
                                </div>
                            </div>
                        )}
                        <div ref={endRef} />
                    </div>

                    {voiceError && <div className="ai-voice-error" role="alert">{voiceError}</div>}
                    <div className="ai-input-row">
                        <textarea
                            ref={inputRef}
                            rows={1}
                            value={text}
                            maxLength={MAX_LEN}
                            placeholder={listening ? "Tinglayapman... gapiring" : "Yozing yoki mikrofonni bosib ayting..."}
                            onChange={(e) => setText(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                        {SpeechRecognition && (
                            <button
                                type="button"
                                className={`ai-mic${listening ? ' ai-mic--on' : ''}`}
                                onClick={toggleListening}
                                disabled={busy || confirming}
                                aria-label={listening ? "Yozib olishni to'xtatish" : "Ovoz bilan yozish"}
                                aria-pressed={listening}
                            >
                                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                                    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                    <rect x="9" y="3" width="6" height="11" rx="3" />
                                    <path d="M5 11a7 7 0 0014 0M12 18v3" />
                                </svg>
                            </button>
                        )}
                        <button type="button" className="ai-send" onClick={send}
                            disabled={busy || confirming || !text.trim()}>
                            Yuborish
                        </button>
                    </div>
                </section>
            )}
        </>
    );
}

export default AssistantChat;
