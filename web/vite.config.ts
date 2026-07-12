import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // dev parity with the nginx container, which proxies /v1 + /health to the
    // API service same-origin (web/nginx.conf)
    proxy: {
      '/v1': 'http://localhost:58000',
      '/health': 'http://localhost:58000',
    },
  },
})
