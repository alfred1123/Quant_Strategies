/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['plotly.js', 'react-plotly.js'],
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_URL ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    pool: 'threads',
  },
})
