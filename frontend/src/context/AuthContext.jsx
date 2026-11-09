import { createContext, useContext, useState } from 'react';
import { clearOfflineCache } from '../offline';
import api from '../api/axios';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(() => {
        const savedUser = localStorage.getItem('user');
        return savedUser ? JSON.parse(savedUser) : null;
    });

    const login = (userData, tokens) => {
        localStorage.setItem('access', tokens.access);
        localStorage.setItem('refresh', tokens.refresh);
        localStorage.setItem('user', JSON.stringify(userData));
        setUser(userData);
    };

    const logout = () => {
        // Refresh token serverda bekor qilinadi (javobni kutmaymiz: internet yo'q bo'lsa ham chiqish ishlayveradi)
        const refresh = localStorage.getItem('refresh');
        if (refresh) api.post('users/logout/', { refresh }, { timeout: 5000 }).catch(() => {});
        localStorage.clear();
        clearOfflineCache(); // telefondagi ma'lumot nusxasi o'chadi; yuborilmagan o'zgarishlar saqlanib qoladi
        setUser(null);
    };

    // Profil tahrirlanganda ism, telefon va email yangilanadi (sarlavhadagi "Salom, ..." ham o'zgaradi)
    const updateUser = (changes) => {
        setUser((prev) => {
            const next = { ...prev, ...changes };
            localStorage.setItem('user', JSON.stringify(next));
            return next;
        });
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, updateUser }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
