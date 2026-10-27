import assert from 'node:assert/strict'
import test from 'node:test'
import { api } from '../src/services/api.js'
import { kioskApi } from '../src/services/kioskApi.js'

for (const sessao of [null, 'sessao-expirada', 'sessao-de-outra-unidade']) {
  test(`formulário consulta, envia e recupera comprovante sem credencial pessoal: ${sessao}`, async () => {
    const anterior = globalThis.localStorage
    globalThis.localStorage = { getItem: () => sessao }
    try {
      const chamadas = []
      const adapter = async (config) => {
        chamadas.push(config)
        return { status: 200, data: { id: 123 }, headers: {}, config }
      }
      const controller = new AbortController()
      await kioskApi.get('/unidade-a/config', { signal: controller.signal, adapter })
      await kioskApi.post('/unidade-a/pedidos', { solicitante_nome: 'Solicitante fictício' }, {
        headers: { 'Idempotency-Key': 'mesma-tentativa' }, adapter,
      })
      await kioskApi.get('/unidade-a/solicitacoes/mesma-tentativa', { adapter })
      for (const config of chamadas) {
        assert.equal(config.baseURL, '/api/public')
        assert.equal(config.headers.has('Authorization'), false)
      }
      assert.equal(chamadas[0].signal, controller.signal)
      assert.equal(chamadas[1].headers.get('Idempotency-Key'), 'mesma-tentativa')
      assert.equal(JSON.parse(chamadas[1].data).solicitante_nome, 'Solicitante fictício')
      assert.deepEqual(chamadas.map((c) => c.url), [
        '/unidade-a/config', '/unidade-a/pedidos', '/unidade-a/solicitacoes/mesma-tentativa',
      ])
    } finally { globalThis.localStorage = anterior }
  })
}

test('falha pública mantém o formulário e a sessão pessoal sem redirecionar', async () => {
  const anterior = globalThis.localStorage
  const janela = globalThis.window
  globalThis.localStorage = { getItem: () => 'sessao-gestao', removeItem: () => assert.fail('Sessão removida') }
  globalThis.window = { location: { set href(_) { assert.fail('Redirecionou ao login') } } }
  try {
    await assert.rejects(kioskApi.post('/unidade-a/pedidos', {}, {
      adapter: async (config) => { throw Object.assign(new Error('Falha pública'), { config, response: { status: 401 } }) },
    }), /Falha pública/)
    assert.equal(globalThis.localStorage.getItem('token'), 'sessao-gestao')
  } finally { globalThis.localStorage = anterior; globalThis.window = janela }
})

test('cliente das áreas restritas continua enviando a credencial pessoal', async () => {
  const anterior = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'sessao-gestao' }
  try {
    await api.get('/auth/me', {
      adapter: async (config) => {
        assert.equal(config.baseURL, '/api')
        assert.equal(config.headers.get('Authorization'), 'Bearer sessao-gestao')
        return { status: 200, data: {}, headers: {}, config }
      },
    })
  } finally { globalThis.localStorage = anterior }
})
