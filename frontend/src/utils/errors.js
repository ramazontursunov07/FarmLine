const FIELD_LABELS = {
    username: 'Username',
    first_name: 'Ism',
    last_name: 'Familiya',
    email: 'Email',
    phone_number: 'Telefon raqam',
    password: 'Parol',
    password2: 'Parolni tasdiqlash',
    name: 'Nomi',
    location: 'Joylashuvi',
    farm_type: 'Turi',
};

export function getErrorMessage(err, fallback = "Xatolik yuz berdi, qayta urinib ko'ring") {
    if (!err.response) return "Serverga ulanib bo'lmadi. Internetni tekshiring.";

    const data = err.response.data;
    if (!data || typeof data !== 'object') return fallback;
    if (typeof data.detail === 'string') return data.detail;

    const [field, value] = Object.entries(data)[0] || [];
    if (!field) return fallback;

    const message = Array.isArray(value) ? value[0] : value;
    const label = FIELD_LABELS[field];
    return label ? `${label}: ${message}` : String(message);
}
