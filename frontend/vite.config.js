import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

// A API confia no proxy local: o cliente não pode escolher o protocolo encaminhado.
function protegerProtocolo(proxy) {
  for (const evento of ['proxyReq', 'proxyReqWs']) {
    proxy.on(evento, (requisicaoProxy, requisicao) => {
      requisicaoProxy.setHeader('X-Forwarded-Proto', requisicao.socket.encrypted ? 'https' : 'http')
    })
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // aceita acesso de outras máquinas na rede
    allowedHosts: ['cnutri.preventsenior.com.br'],
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url))] },
    proxy: {
      '^/api(?:/|\\?|$)': { target: 'http://127.0.0.1:8000', changeOrigin: true, xfwd: true, configure: protegerProtocolo },
      '^/ws(?:/|\\?|$)': { target: 'ws://127.0.0.1:8000', ws: true, xfwd: true, configure: protegerProtocolo },
    },
  },
})
