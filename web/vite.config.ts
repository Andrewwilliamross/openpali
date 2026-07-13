/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Playwright specs (e2e/) run in the containerized browser job, not vitest
  test: {
    exclude: ['e2e/**', 'node_modules/**'],
  },
  server: {
    // dev parity with the nginx container, which proxies /v1 + /health to the
    // API service same-origin (web/nginx.conf)
    proxy: {
      '/v1': 'http://localhost:58000',
      '/health': 'http://localhost:58000',
    },
  },
})
