import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api/axios';
import { useAuth } from '../context/AuthContext';

function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const response = await api.post('users/login/', {
                username,
                password,
            });

            const { access, refresh } = response.data;

            // Token orqali foydalanuvchi ma'lumotini olish uchun profilni so'raymiz
            const profileResponse = await api.get('users/profile/', {
                headers: { Authorization: `Bearer ${access}` },
            });

            login(profileResponse.data, { access, refresh });
            navigate('/dashboard');
        } catch (err) {
            setError('Login yoki parol noto\'g\'ri');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>
            <h2>Kirish</h2>
            <form onSubmit={handleSubmit}>
                <div>
                    <label>Username</label>
                    <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        required
                    />
                </div>
                <div>
                    <label>Parol</label>
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                    />
                </div>
                {error && <p style={{ color: 'red' }}>{error}</p>}
                <button type="submit" disabled={loading}>
                    {loading ? 'Kuting...' : 'Kirish'}
                </button>
            </form>
            <p>
                Hisobingiz yo'qmi? <Link to="/register">Ro'yxatdan o'tish</Link>
            </p>
        </div>
    );
}

export default Login;
