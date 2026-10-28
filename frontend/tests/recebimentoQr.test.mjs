import assert from 'node:assert/strict'
import test from 'node:test'
import { codigoRecebimentoValido, guardarCodigoRecebimento, limparCodigoRecebimento, nomeRecebedorValido, recebimentoApi, recuperarCodigoRecebimento, registroRecebimentoValido } from '../src/services/recebimentoQr.js'
import { api } from '../src/services/api.js'

test('recebimento depende do código exclusivo da filipeta e de registro profissional preenchido', () => {
  assert.equal(codigoRecebimentoValido('a'.repeat(43)), true)
  for (const codigo of ['', '123', 'a'.repeat(44), '../admin']) assert.equal(codigoRecebimentoValido(codigo), false)
  for (const registro of ['COREN-SP 123456', 'CRM/RJ 1234', '123456', '  coren 1234  ']) assert.equal(registroRecebimentoValido(registro), true)
  for (const registro of ['', '   ', 'abc', '123\nABC', 'A'.repeat(51)]) assert.equal(registroRecebimentoValido(registro), false)
})

test('identificação exige nome e aceita acentos, apóstrofos e sobrenomes compostos', () => {
  for (const nome of ['João da Conceição', "Érica D'Ávila-Souza", '  José  Luís  ', 'Ana', 'A'.repeat(120)]) assert.equal(nomeRecebedorValido(nome), true)
  for (const nome of ['', '   ', 'A', 'A  ', '12345', '=João', 'João\nSilva', '<Pessoa>', 'A'.repeat(121)]) assert.equal(nomeRecebedorValido(nome), false)
})

test('consulta do QR Code não envia credencial pessoal; ações exigem a sessão da copeira', async () => {
  const anterior = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'expirado', removeItem: () => assert.fail('Sessão pessoal removida') }
  try {
    await recebimentoApi.post('/consultar', { codigo: 'a'.repeat(43) }, {
      adapter: async (config) => {
        assert.equal(config.headers.has('Authorization'), false)
        assert.equal(config.baseURL, '/api/recebimentos')
        assert.deepEqual(JSON.parse(config.data), { codigo: 'a'.repeat(43) })
        return { status: 200, data: {}, headers: {}, config }
      },
    })
    for (const acao of ['identificar', 'confirmar']) await api.post(`/recebimentos/${acao}`, { codigo: 'a'.repeat(43) }, {
      adapter: async config => {
        assert.equal(config.headers.get('Authorization'), 'Bearer expirado')
        return { status: 200, data: {}, headers: {}, config }
      },
    })
  } finally { globalThis.localStorage = anterior }
})

test('QR Code retorna à mesma refeição após login sem incluir seu código na URL de login', () => {
  const valores = new Map()
  const s = { getItem: k => valores.get(k), setItem: (k, v) => valores.set(k, v), removeItem: k => valores.delete(k) }
  guardarCodigoRecebimento('a'.repeat(43), s)
  assert.equal(recuperarCodigoRecebimento(s), 'a'.repeat(43))
  guardarCodigoRecebimento('https://externo.test', s)
  assert.equal(recuperarCodigoRecebimento(s), 'a'.repeat(43))
  limparCodigoRecebimento(s)
  assert.equal(recuperarCodigoRecebimento(s), '')
})
