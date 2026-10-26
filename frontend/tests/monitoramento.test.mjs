import test from 'node:test'
import assert from 'node:assert/strict'
import { estadoSondas, tamanhoLegivel, tempoAtivo } from '../src/services/monitoramento.js'

const ok = { status: 'fulfilled', value: { status: 200 } }
test('API respondendo e banco indisponível são estados distintos', () => {
  assert.deepEqual(estadoSondas(ok, ok), { api: 'RESPONDENDO', banco: 'CONECTADO' })
  assert.deepEqual(estadoSondas(ok, { status: 'rejected', reason: { response: { status: 503 } } }), { api: 'RESPONDENDO', banco: 'INDISPONIVEL' })
})
test('falha de rede deixa a API indisponível e a situação do banco desconhecida', () => {
  const falha = { status: 'rejected', reason: {} }
  assert.deepEqual(estadoSondas(falha, falha), { api: 'INDISPONIVEL', banco: 'DESCONHECIDO' })
})
test('tempo ativo e tamanho não inventam números para valores ausentes', () => {
  assert.equal(tamanhoLegivel(null), 'Não informado')
  assert.equal(tempoAtivo(undefined), 'Não informado')
  assert.equal(tamanhoLegivel(1024 ** 3), '1 GiB')
  assert.equal(tempoAtivo(90061), '1d 1h 1min')
})
