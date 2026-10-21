// Dashboard uchun umumiy kichik bo'laklar: ikonkalar va sana/salomlashish yordamchilari.

const PATHS = {
    work: 'M5 4h11l3 3v13H5V4zm3 6h8M8 14h8M8 18h5',
    tasks: 'M4 6l2 2 3-3M4 14l2 2 3-3M12 7h8M12 15h8',
    stock: 'M3 8l9-4 9 4-9 4-9-4zm0 0v8l9 4 9-4V8M12 12v8',
    money: 'M3 7h18v12H3V7zm0 4h18M16 15h2',
    debt: 'M12 3v18M16 7.5c0-1.4-1.8-2.5-4-2.5s-4 1.1-4 2.5 1.8 2.5 4 2.5 4 1.1 4 2.5-1.8 2.5-4 2.5-4-1.1-4-2.5',
    lock: 'M6 11h12v9H6v-9zm3 0V8a3 3 0 016 0v3',
    clock: 'M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z',
    care: 'M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z',
    check: 'M5 12.5l4.5 4.5L19 7.5',
    plus: 'M12 5v14M5 12h14',
    chevron: 'M9 5l7 7-7 7',
    tag: 'M3 12V4h8l9 9-8 8-9-9zM7.5 7.5h.01',
    users: 'M9 11a3 3 0 100-6 3 3 0 000 6zM3 20a6 6 0 0112 0M16.5 11a2.5 2.5 0 100-5M21 19a5 5 0 00-4-4.9',
};

export function Icon({ name, size = 20, className }) {
    return (
        <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={PATHS[name]} />
        </svg>
    );
}
