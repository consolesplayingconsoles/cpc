import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    // Distinct *.localhost origins so the browser's password manager keeps Pluto's
    // DreameHome logins separate (and treats Pluto as its own origin):
    //   dev  -> http://pluto.dev.localhost:5173   (start.sh — Vite HMR)
    //   prod -> http://pluto.localhost            (serve.sh — built dist/)
    // Any sub-label of `.localhost` resolves to loopback in the browser.
    allowedHosts: ['localhost', '.localhost'],
  },
})
