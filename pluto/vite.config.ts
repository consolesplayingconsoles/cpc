import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    // Allow http://pluto.localhost:5174 so the browser's password manager treats
    // Pluto as its own origin (distinct from a bare localhost) for the DreameHome login.
    allowedHosts: ['localhost', 'pluto.localhost', '.localhost'],
  },
})
