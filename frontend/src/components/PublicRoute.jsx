import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Kirgan foydalanuvchi /login yoki /register ga qaytib kirmasligi uchun
function PublicRoute({ children }) {
    const { user } = useAuth();
    return user ? <Navigate to="/dashboard" replace /> : children;
}

export default PublicRoute;
