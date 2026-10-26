import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function PrivateRoute({ children }) {
    const { user } = useAuth();
    const location = useLocation();

    if (!user) {
        // Kirgandan keyin shu sahifaga qaytish uchun (masalan, QR kod skanerlanganda)
        return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
    }

    return children;
}

export default PrivateRoute;
