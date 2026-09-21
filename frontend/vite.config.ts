/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['plotly.js', 'react-plotly.js'],
    // The maplibre-gl override (^6, for the audit fix) is ESM-only and exports
    // "." under `import` alone, so pre-bundling plotly.js fails to resolve it
    // under the `require` condition. It is only reached by plotly's map traces,
    // which this app does not render.
    exclude: ['maplibre-gl'],
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_URL ?? 'http://localhost:8000',
      // Health probes (login page) — same-origin via Vite avoids WSL localhost split.
      '/health': {
        target: process.env.VITE_API_URL ?? 'http://localhost:8000',
        changeOrigin: true,
      },
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
