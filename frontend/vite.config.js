import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // aceita acesso de outras máquinas na rede
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url))] },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, xfwd: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true, xfwd: true },
    },
  },
})
