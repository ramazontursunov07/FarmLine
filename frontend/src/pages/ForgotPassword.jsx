import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api/axios';
import { getErrorMessage } from '../utils/errors';

function ForgotPassword() {
    const [username, setUsername] = useState('');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');
        setLoading(true);

        try {
            const { data } = await api.post('users/forgot-password/', { username });
            setMessage(data.detail);
        } catch (err) {
            setError(getErrorMessage(err, "So'rov yuborib bo'lmadi"));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-page">
            <div className="auth-card">
                <h2>Parolni tiklash</h2>
                <p className="workers-hint">
                    Username'ingizni kiriting. Tiklash havolasi Profil bo'limida ulagan Telegramingizga yuboriladi.
                </p>
                <form onSubmit={handleSubmit}>
                    <div className="form-field">
                        <label>Username</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            required
                        />
                    </div>
                    {error && <p className="error-text" role="alert">{error}</p>}
                    {message && <p className="success-text" role="status">{message}</p>}
                    <button type="submit" className="btn-primary" disabled={loading}>
                        {loading ? 'Kuting...' : 'Havola yuborish'}
                    </button>
                </form>
                <p className="auth-footer">
                    <Link to="/login">← Kirishga qaytish</Link>
                </p>
            </div>
        </div>
    );
}

export default ForgotPassword;
