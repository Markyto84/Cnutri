import assert from 'node:assert/strict'
import test from 'node:test'
import { chaveSalva, concluirTentativa, criarChaveEnvio, obterChaveEnvio, textoImpressao } from '../src/services/solicitacoes.js'

const salvos = new Map()
globalThis.sessionStorage = { getItem: (k) => salvos.get(k), setItem: (k, v) => salvos.set(k, v), removeItem: (k) => salvos.delete(k) }

test('a tentativa mantém a chave após falha e só muda quando começa outra solicitação', () => {
  const inicial = obterChaveEnvio('teste')
  assert.match(inicial, /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)
  assert.equal(obterChaveEnvio('teste'), inicial)
  assert.equal(chaveSalva('teste'), inicial)
  assert.notEqual(obterChaveEnvio('outra-unidade'), inicial)
  concluirTentativa('teste')
  assert.notEqual(obterChaveEnvio('teste'), inicial)
  assert.equal(salvos.size, 2) // somente chaves; nenhum campo ou nome do formulário.
})

test('criação não depende de crypto.randomUUID nem do contexto HTTPS legado', () => {
  assert.notEqual(criarChaveEnvio(), criarChaveEnvio())
})

test('armazenamento bloqueado permite repetir com a mesma chave em memória', () => {
  const anterior = globalThis.sessionStorage
  globalThis.sessionStorage = { getItem() { throw Error() }, setItem() { throw Error() }, removeItem() { throw Error() } }
  try {
    const chave = obterChaveEnvio('sem-storage')
    assert.equal(obterChaveEnvio('sem-storage'), chave)
    concluirTentativa('sem-storage')
    assert.notEqual(obterChaveEnvio('sem-storage'), chave)
  } finally { globalThis.sessionStorage = anterior }
})

test('pendência, falha e envio incerto não confirmam impressão física', () => {
  for (const estado of ['PENDENTE', 'FALHA', 'INCERTO']) assert.doesNotMatch(textoImpressao(estado), /enviada|impressa com sucesso/i)
})
