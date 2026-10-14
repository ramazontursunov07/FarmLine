import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import App from './App.jsx';
import { AuthProvider } from './context/AuthContext.jsx';
import { initInstallCapture } from './offline/install';

// Brauzerning o'rnatish hodisasi sahifa ochilishi bilan keladi: React'dan oldin ushlab qolamiz
initInstallCapture();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);

// Service worker: ilova qobig'ini (HTML/JS/CSS) telefonda saqlaydi, shuning uchun ilova internetsiz ochiladi.
// Ishlab chiqarishda (build) yoqiladi; dev rejimida Vite HMR bilan to'qnashmasligi uchun o'chiq.
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((err) => console.warn('Service worker ishga tushmadi:', err));
  });
}
