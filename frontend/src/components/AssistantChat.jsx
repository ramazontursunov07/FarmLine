import { useEffect, useRef, useState } from 'react';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';
import './AssistantChat.css';

const GREETING =
    "Salom! Men FarmLine yordamchisiman. Chorvachilik va parrandachilik bo'yicha savol bering.";
const MAX_LEN = 1000; // backend ham shu chegarani tekshiradi
const HISTORY_LIMIT = 10; // AI ga oxirgi nechta xabar yuboriladi
const AI_TIMEOUT_MS = 60000; // AI javobi oddiy so'rovdan sekinroq bo'lishi mumkin

// Ekranning pastki o'ng burchagidagi "AI bilan suhbat" tugmasi va chat oynasi.
function AssistantChat() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([]); // { role: 'user' | 'assistant', content, error? }
    const [text, setText] = useState('');
    const [busy, setBusy] = useState(false);
    const endRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, busy, open]);

    useEffect(() => {
        if (open) inputRef.current?.focus();
    }, [open]);

    const send = async () => {
        const question = text.trim();
        if (!question || busy) return;

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
            setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    error: true,
                    content: getErrorMessage(err, "AI javob bera olmadi, birozdan keyin qayta urinib ko'ring."),
                },
            ]);
        } finally {
            setBusy(false);
        }
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
                                <button type="button" className="ai-link-btn" onClick={() => setMessages([])}
                                    disabled={busy}>
                                    Tozalash
                                </button>
                            )}
                            <button type="button" className="ai-close" onClick={() => setOpen(false)}
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
                        <div ref={endRef} />
                    </div>

                    <div className="ai-input-row">
                        <textarea
                            ref={inputRef}
                            rows={1}
                            value={text}
                            maxLength={MAX_LEN}
                            placeholder="Savolingizni yozing..."
                            onChange={(e) => setText(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                        <button type="button" className="ai-send" onClick={send}
                            disabled={busy || !text.trim()}>
                            Yuborish
                        </button>
                    </div>
                </section>
            )}
        </>
    );
}

export default AssistantChat;
