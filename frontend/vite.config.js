import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // tarmoqdagi boshqa qurilmalar (telefon) ham ochishi uchun
    allowedHosts: true, // tunnel domenlariga (cloudflare, ngrok) ruxsat
    proxy: {
      // /api so'rovlarini Django'ga uzatadi: telefon faqat bitta manzilni ishlatadi
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
