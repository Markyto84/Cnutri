import assert from 'node:assert/strict'
import test from 'node:test'
import { codigoRecebimentoValido, recebimentoApi, registroRecebimentoValido } from '../src/services/recebimentoQr.js'

test('recebimento depende do código exclusivo da filipeta e de registro profissional preenchido', () => {
  assert.equal(codigoRecebimentoValido('a'.repeat(43)), true)
  for (const codigo of ['', '123', 'a'.repeat(44), '../admin']) assert.equal(codigoRecebimentoValido(codigo), false)
  for (const registro of ['COREN-SP 123456', 'CRM/RJ 1234', '123456', '  coren 1234  ']) assert.equal(registroRecebimentoValido(registro), true)
  for (const registro of ['', '   ', 'abc', '123\nABC', 'A'.repeat(51)]) assert.equal(registroRecebimentoValido(registro), false)
})

test('QR Code funciona com sessão pessoal expirada sem enviar a credencial nem mudar o login', async () => {
  const anterior = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'expirado', removeItem: () => assert.fail('Sessão pessoal removida') }
  try {
    await recebimentoApi.post('/confirmar', { codigo: 'a'.repeat(43), registro_profissional: 'COREN 123' }, {
      adapter: async (config) => {
        assert.equal(config.headers.has('Authorization'), false)
        assert.equal(config.baseURL, '/api/recebimentos')
        assert.deepEqual(JSON.parse(config.data), { codigo: 'a'.repeat(43), registro_profissional: 'COREN 123' })
        return { status: 200, data: {}, headers: {}, config }
      },
    })
  } finally { globalThis.localStorage = anterior }
})
