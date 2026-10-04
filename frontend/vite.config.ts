import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The API runs on :8000 in development; same-origin keeps the session cookies simple.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
