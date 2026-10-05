import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Django runs on :8000 — the browser only ever talks to Vite, so no CORS setup is needed.
    // changeOrigin sends Host: 127.0.0.1:8000, so phones on Wi-Fi (npm run dev:lan) pass Django's ALLOWED_HOSTS.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
