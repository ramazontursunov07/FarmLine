import axios from 'axios';

// Odatda nisbiy yo'l: so'rovlar frontend manzilining o'ziga yuboriladi (Vite proxy yoki nginx Django'ga uzatadi).
// Kerak bo'lsa, frontend/.env faylida VITE_API_URL=https://api.sizning-domen.uz/api/ deb o'zgartirish mumkin.
const API_URL = import.meta.env.VITE_API_URL || '/api/';

const api = axios.create({
    baseURL: API_URL,
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

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = localStorage.getItem('refresh');

                const response = await axios.post(
                    `${API_URL}users/token/refresh/`,
                    { refresh: refreshToken }
                );

                const newAccessToken = response.data.access;
                localStorage.setItem('access', newAccessToken);

                originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                return api(originalRequest);
            } catch (refreshError) {
                localStorage.clear();
                window.location.href = '/login';
                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

export default api;
