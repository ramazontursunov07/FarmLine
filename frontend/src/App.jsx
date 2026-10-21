import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Finance from './pages/Finance';
import Debts from './pages/Debts';
import FarmWork from './pages/FarmWork';
import AnimalCards from './pages/AnimalCards';
import AnimalCard from './pages/AnimalCard';
import Tasks from './pages/Tasks';
import Inventory from './pages/Inventory';
import Profile from './pages/Profile';
import PrivateRoute from './components/PrivateRoute';
import PublicRoute from './components/PublicRoute';
import OfflineBanner from './components/OfflineBanner';
import { useOfflineState } from './offline/state';
import './App.css';

function App() {
    // Navbatdagi o'zgarishlar serverga yuborilgach, sahifalar yangi ma'lumotni qayta yuklashi uchun qayta ochiladi
    const { syncVersion } = useOfflineState();
    return (
        <>
        <Routes key={syncVersion}>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
            <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
            <Route path="/forgot-password" element={<PublicRoute><ForgotPassword /></PublicRoute>} />
            {/* Telegramdagi havola kirgan foydalanuvchida ham ochilishi kerak, shuning uchun PublicRoute yo'q */}
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route
                path="/dashboard"
                element={
                    <PrivateRoute>
                        <Dashboard />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/work"
                element={
                    <PrivateRoute>
                        <FarmWork />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/animals"
                element={
                    <PrivateRoute>
                        <AnimalCards />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/animals/:animalId"
                element={
                    <PrivateRoute>
                        <AnimalCard />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/tasks"
                element={
                    <PrivateRoute>
                        <Tasks />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/inventory"
                element={
                    <PrivateRoute>
                        <Inventory />
                    </PrivateRoute>
                }
            />

            <Route
                path="/profile"
                element={
                    <PrivateRoute>
                        <Profile />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/finance"
                element={
                    <PrivateRoute>
                        <Finance />
                    </PrivateRoute>
                }
            />

            <Route
                path="/farms/:farmId/debts"
                element={
                    <PrivateRoute>
                        <Debts />
                    </PrivateRoute>
                }
            />

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
        <OfflineBanner />
        </>
    );
}

export default App;
