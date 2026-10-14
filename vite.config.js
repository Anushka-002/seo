import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    // In dev the API runs on :8000; in production FastAPI serves this build on the same origin.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
