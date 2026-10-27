import assert from 'node:assert/strict'
import test from 'node:test'
import { cozinhaApi } from '../src/services/cozinhaApi.js'

test('cozinha opera sem enviar a sessão pessoal, inclusive se houver credencial antiga no navegador', async () => {
  const anterior = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'sessao-antiga' }
  try {
    let enviada
    await cozinhaApi.patch('/unidades/1/pedidos/2/status', { status: 'EM_PREPARO' }, {
      adapter: async (config) => { enviada = config; return { status: 200, data: {}, headers: {}, config } },
    })
    assert.equal(enviada.baseURL, '/api/cozinha')
    assert.equal(enviada.headers.has('Authorization'), false)
    assert.equal(enviada.url, '/unidades/1/pedidos/2/status')
  } finally { globalThis.localStorage = anterior }
})

test('falha da cozinha não remove credenciais da gestão nem redireciona para login', async () => {
  const anterior = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'sessao-gestao', removeItem: () => assert.fail('Sessão pessoal removida') }
  try {
    await assert.rejects(cozinhaApi.get('/unidades/1/estado', {
      adapter: async () => { throw Object.assign(new Error('Falha de serviço'), { response: { status: 401 } }) },
    }), /Falha de serviço/)
    assert.equal(globalThis.localStorage.getItem('token'), 'sessao-gestao')
  } finally { globalThis.localStorage = anterior }
})
