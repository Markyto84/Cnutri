import assert from 'node:assert/strict'
import test from 'node:test'
import { unidadesPublicasApi } from '../src/services/unidadesPublicas.js'

test('entrada pública carrega unidades sem anexar sessão pessoal ou redirecionar ao login', async () => {
  const anterior = globalThis.localStorage
  const janela = globalThis.window
  globalThis.localStorage = { getItem: () => 'sessao-expirada', removeItem: () => assert.fail('Sessão pessoal apagada') }
  globalThis.window = { location: { set href(_) { assert.fail('Redirecionamento ao login') } } }
  try {
    const controller = new AbortController()
    await unidadesPublicasApi.get('/unidades', {
      signal: controller.signal,
      adapter: async (config) => {
        assert.equal(config.baseURL, '/api/operacao')
        assert.equal(config.url, '/unidades')
        assert.equal(config.headers.has('Authorization'), false)
        assert.equal(config.signal, controller.signal)
        return { status: 200, data: [], headers: {}, config }
      },
    })
    await assert.rejects(unidadesPublicasApi.get('/unidades', {
      adapter: async (config) => { throw Object.assign(new Error('Falha de conexão'), { config, response: { status: 401 } }) },
    }), /Falha de conexão/)
  } finally { globalThis.localStorage = anterior; globalThis.window = janela }
})
