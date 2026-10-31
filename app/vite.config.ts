import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiPort = Number(process.env.API_PORT ?? 8787)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Local only. Teammates reach it through `tailscale serve`, which proxies to localhost.
    host: '127.0.0.1',
    allowedHosts: ['.ts.net'],
    port: Number(process.env.APP_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
    },
  },
})
