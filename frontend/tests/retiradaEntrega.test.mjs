import test from 'node:test'
import assert from 'node:assert/strict'
import { consumirRetirada, etapaEntrega, guardarRetirada, limparRetirada } from '../src/services/retiradaEntrega.js'

function armazenamento() {
  const mapa = new Map()
  return { getItem: k => mapa.get(k) ?? null, setItem: (k, v) => mapa.set(k, v), removeItem: k => mapa.delete(k) }
}

test('primeira retirada continua uma única vez após login, somente na unidade escolhida', () => {
  const s = armazenamento()
  guardarRetirada('2', 32, s, 1000)
  assert.equal(consumirRetirada('2', s, 2000), 32)
  assert.equal(consumirRetirada('2', s, 2000), null)
  guardarRetirada(2, 33, s, 1000)
  assert.equal(consumirRetirada(3, s, 2000), null)
  assert.equal(consumirRetirada(2, s, 2000), null)
})

test('intenção expirada, futura, corrompida ou encerrada no logout não retira refeições', () => {
  const s = armazenamento()
  guardarRetirada(2, 32, s, 1000)
  assert.equal(consumirRetirada(2, s, 301000), null)
  guardarRetirada(2, 32, s, 1000)
  assert.equal(consumirRetirada(2, s, 900), null)
  s.setItem('cnutri-retirada-apos-login', 'inválido')
  assert.equal(consumirRetirada(2, s, 1000), null)
  guardarRetirada(2, 32, s, 1000); limparRetirada(s)
  assert.equal(consumirRetirada(2, s, 2000), null)
})

test('retirada apresenta Em entrega até o recebimento, preservando cancelamento e conclusão', () => {
  assert.equal(etapaEntrega({ status: 'PRONTO' }), 'PRONTO')
  assert.equal(etapaEntrega({ status: 'PRONTO', retirada: { copeira_nome: 'Fictícia' } }), 'EM_ENTREGA')
  assert.equal(etapaEntrega({ status: 'PRONTO', em_entrega: true }), 'EM_ENTREGA')
  assert.equal(etapaEntrega({ status: 'ENTREGUE', retirada: {} }), 'ENTREGUE')
  assert.equal(etapaEntrega({ status: 'CANCELADO', retirada: {} }), 'CANCELADO')
})
