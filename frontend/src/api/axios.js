import axios from 'axios';
import { clearOfflineCache, installOffline } from '../offline';

// Odatda nisbiy yo'l: so'rovlar frontend manzilining o'ziga yuboriladi (Vite proxy yoki nginx Django'ga uzatadi).
// Kerak bo'lsa, frontend/.env faylida VITE_API_URL=https://api.sizning-domen.uz/api/ deb o'zgartirish mumkin.
const API_URL = import.meta.env.VITE_API_URL || '/api/';

// Qishloqda tarmoq sust bo'lishi mumkin: javob kelmasa, so'rov abadiy osilib qolmasin
const TIMEOUT_MS = 20000;

const api = axios.create({
    baseURL: API_URL,
    timeout: TIMEOUT_MS,
});

api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Bir vaqtda ko'p so'rov 401 olsa (masalan, internet qaytganda), token faqat BIR marta yangilanadi
let refreshPromise = null;

function refreshAccessToken() {
    if (!refreshPromise) {
        refreshPromise = axios
            .post(
                `${API_URL}users/token/refresh/`,
                { refresh: localStorage.getItem('refresh') },
                { timeout: TIMEOUT_MS }
            )
            .then(({ data }) => {
                localStorage.setItem('access', data.access);
                // Server har safar yangi refresh token beradi: sessiya foydalanish davomida uzayib boradi
                if (data.refresh) localStorage.setItem('refresh', data.refresh);
                return data.access;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }
    return refreshPromise;
}

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        // Yangilanadigan token bo'lmasa (masalan, login paytida noto'g'ri parol), 401 ni o'zidek qaytaramiz
        if (error.response?.status === 401 && !originalRequest._retry && localStorage.getItem('refresh')) {
            originalRequest._retry = true;

            try {
                const newAccessToken = await refreshAccessToken();
                originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                return api(originalRequest);
            } catch (refreshError) {
                // Faqat server "sessiya yaroqsiz" desa chiqaramiz. Internet yo'qligi yoki server xatosi
                // sessiya tugaganini bildirmaydi: foydalanuvchi tizimda qoladi, so'rov oddiy xato bilan tugaydi.
                const status = refreshError.response?.status;
                if (status === 400 || status === 401 || status === 403) {
                    localStorage.clear();
                    clearOfflineCache().finally(() => {
                        window.location.href = '/login';
                    });
                }
                if (!refreshError.response) {
                    // Token yangilash paytida internet uzildi: asl so'rov offline qatlamiga (kesh/navbat) o'tadi
                    error.isRefreshNetworkError = true;
                    return Promise.reject(error);
                }
                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

// Eng oxirida: offline qatlami yuqoridagi interceptorlardan keyin ishlashi kerak
installOffline(api);

export default api;
