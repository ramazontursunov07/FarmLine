import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Finance from './pages/Finance';
import FarmWork from './pages/FarmWork';
import Tasks from './pages/Tasks';
import Inventory from './pages/Inventory';
import Profile from './pages/Profile';
import PrivateRoute from './components/PrivateRoute';
import PublicRoute from './components/PublicRoute';
import './App.css';

function App() {
    return (
        <Routes>
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

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
    );
}

export default App;
