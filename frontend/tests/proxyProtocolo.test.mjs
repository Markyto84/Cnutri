import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import config from '../vite.config.js'

for (const caminho of ['/api', '/ws']) {
  const [padrao, opcoes] = Object.entries(config.server.proxy).find(([padrao]) => new RegExp(padrao).test(caminho))
  test(`${caminho}: o protocolo real prevalece sobre cabeçalho forjado pelo cliente`, () => {
    const proxy = new EventEmitter()
    opcoes.configure(proxy)
    for (const evento of ['proxyReq', 'proxyReqWs']) {
      for (const encrypted of [false, true]) {
        const headers = { 'X-Forwarded-Proto': encrypted ? 'http' : 'https' }
        proxy.emit(evento, { setHeader: (nome, valor) => { headers[nome] = valor } }, { socket: { encrypted } })
        assert.equal(headers['X-Forwarded-Proto'], encrypted ? 'https' : 'http')
      }
    }
  })

  test(`${caminho}: só o prefixo completo é encaminhado, sem capturar nomes de unidades`, () => {
    const corresponde = new RegExp(padrao)
    for (const url of [caminho, caminho + '/', caminho + '/unidades', caminho + '?consulta=1']) assert.equal(corresponde.test(url), true)
    for (const url of [caminho + '-hospital', caminho + 'hospital', '/unidade' + caminho]) assert.equal(corresponde.test(url), false)
  })
}
