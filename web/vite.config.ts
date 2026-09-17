import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// API_PORT lets `npm run dev` reach a locally running API on a custom port.
const apiTarget = `http://localhost:${process.env.API_PORT ?? 8000}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
