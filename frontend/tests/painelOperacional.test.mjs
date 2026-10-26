import test from 'node:test'
import assert from 'node:assert/strict'
import { atrasoPedido, filtrarPedidos, FILTROS_VAZIOS, dataBrasilia } from '../src/services/painelOperacional.js'

const pedidos = [
  { id: 42, nome_paciente: 'João Fictício', tipo_solicitacao: 'PACIENTE', leito: '402', dados_dinamicos: { andar: '4º ANDAR', refeicao: 'ALMOÇO' } },
  { id: 99, solicitante_nome: 'Médica Fictícia', tipo_solicitacao: 'MEDICO', dados_dinamicos: { refeicao: 'MAMINHA ASSADA' } },
  { id: 43, nome_paciente: 'Outra Pessoa', tipo_solicitacao: 'PACIENTE', leito: '302', dados_dinamicos: { andar: '3º ANDAR', refeicao: 'JANTAR' } },
]
const filtrar = (filtros) => filtrarPedidos(pedidos, { ...FILTROS_VAZIOS, ...filtros }).map((p) => p.id)

test('pesquisa ignora acentos e distingue pedido, nome e leito', () => {
  assert.deepEqual(filtrar({ busca: 'joao ficticio' }), [42])
  assert.deepEqual(filtrar({ busca: '#99' }), [99])
  assert.deepEqual(filtrar({ busca: '402' }), [42])
  assert.deepEqual(filtrar({ busca: '  MEDICA  ' }), [99])
})
test('filtros por andar, leito, tipo e refeição combinam sem mudar a lista original', () => {
  assert.deepEqual(filtrar({ andar: '4º ANDAR', leito: '402', tipo: 'PACIENTE', refeicao: 'ALMOÇO' }), [42])
  assert.deepEqual(filtrar({ tipo: 'MEDICO', andar: '4º ANDAR' }), [])
  assert.deepEqual(filtrar({}), [42, 99, 43])
  assert.equal(pedidos.length, 3)
})

const agora = Date.parse('2026-10-26T15:00:00Z')
const limites = { preparo_minutos: 30, entrega_minutos: 30 }
test('preparo conta desde a solicitação e alerta no limite de trinta minutos', () => {
  for (const status of ['PENDENTE', 'EM_PREPARO']) {
    assert.equal(atrasoPedido({ status, criado_em: '2026-10-26T14:30:01Z' }, limites, agora), null)
    assert.deepEqual(atrasoPedido({ status, criado_em: '2026-10-26T14:30:00' }, limites, agora), { etapa: 'Preparo', minutos: 30, limite: 30 })
  }
})
test('entrega conta desde pronto; não usa o tempo de preparo ou horário local', () => {
  const pedido = { status: 'PRONTO', criado_em: '2026-10-25T00:00:00Z', concluido_em: '2026-10-26T11:40:00-03:00' }
  assert.equal(atrasoPedido(pedido, limites, agora), null)
  assert.deepEqual(atrasoPedido({ ...pedido, concluido_em: '2026-10-26T14:20:00Z' }, limites, agora), { etapa: 'Entrega', minutos: 40, limite: 30 })
  assert.equal(atrasoPedido({ ...pedido, concluido_em: null }, limites, agora), null)
})
test('prazo editado e desativado e estados finais não geram falso alerta', () => {
  const pedido = { status: 'EM_PREPARO', criado_em: '2026-10-26T14:10:00Z' }
  assert.equal(atrasoPedido(pedido, { preparo_minutos: 60 }, agora), null)
  assert.equal(atrasoPedido(pedido, { preparo_minutos: null }, agora), null)
  for (const status of ['ENTREGUE', 'CANCELADO']) assert.equal(atrasoPedido({ ...pedido, status }, limites, agora), null)
  assert.equal(atrasoPedido({ ...pedido, criado_em: 'inválida' }, limites, agora), null)
  assert.equal(atrasoPedido({ ...pedido, criado_em: '2026-10-27T00:00:00Z' }, limites, agora), null)
})
test('datas de filtro seguem Brasília na virada do dia', () => {
  assert.equal(dataBrasilia('2026-10-27T02:59:59Z'), '2026-10-26')
  assert.equal(dataBrasilia('2026-10-27T03:00:00Z'), '2026-10-27')
})
