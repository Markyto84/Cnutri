import test from 'node:test'
import assert from 'node:assert/strict'
import { etapaEntrega, limparRetirada } from '../src/services/retiradaEntrega.js'

function armazenamento() {
  const mapa = new Map()
  return { getItem: k => mapa.get(k) ?? null, setItem: (k, v) => mapa.set(k, v), removeItem: k => mapa.delete(k) }
}

test('logout limpa intenções antigas do painel sem criar novas retiradas', () => {
  const s = armazenamento()
  s.setItem('cnutri-retirada-apos-login', '{"pedidoId":32}')
  limparRetirada(s)
  assert.equal(s.getItem('cnutri-retirada-apos-login'), null)
})

test('retirada apresenta Em entrega até o recebimento, preservando cancelamento e conclusão', () => {
  assert.equal(etapaEntrega({ status: 'PRONTO' }), 'PRONTO')
  assert.equal(etapaEntrega({ status: 'PRONTO', retirada: { copeira_nome: 'Fictícia' } }), 'EM_ENTREGA')
  assert.equal(etapaEntrega({ status: 'PRONTO', em_entrega: true }), 'EM_ENTREGA')
  assert.equal(etapaEntrega({ status: 'ENTREGUE', retirada: {} }), 'ENTREGUE')
  assert.equal(etapaEntrega({ status: 'CANCELADO', retirada: {} }), 'CANCELADO')
})
