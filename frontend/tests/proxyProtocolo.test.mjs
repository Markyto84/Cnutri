import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import config from '../vite.config.js'

for (const caminho of ['/api', '/ws']) {
  test(`${caminho}: o protocolo real prevalece sobre cabeçalho forjado pelo cliente`, () => {
    const proxy = new EventEmitter()
    config.server.proxy[caminho].configure(proxy)
    for (const evento of ['proxyReq', 'proxyReqWs']) {
      for (const encrypted of [false, true]) {
        const headers = { 'X-Forwarded-Proto': encrypted ? 'http' : 'https' }
        proxy.emit(evento, { setHeader: (nome, valor) => { headers[nome] = valor } }, { socket: { encrypted } })
        assert.equal(headers['X-Forwarded-Proto'], encrypted ? 'https' : 'http')
      }
    }
  })
}
