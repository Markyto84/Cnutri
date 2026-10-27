import assert from 'node:assert/strict'
import test from 'node:test'
import { corpoPedido } from '../src/services/prescricao.js'

const original = { tipo_solicitacao: 'PACIENTE', solicitante_nome: 'Solicitante original',
  solicitante_identificacao: 'COREN TESTE', dieta_id: 1, prescricao: { referencia: 'Referência anterior' } }

test('correção preserva o solicitante e envia os dados operacionais do formulário', () => {
  const corpo = corpoPedido({ nome_paciente: 'Paciente teste', dieta_id: '2', para: 'Acompanhante', cardapio: 'GERAL' }, original)
  assert.equal(corpo.solicitante_nome, original.solicitante_nome)
  assert.equal(corpo.solicitante_identificacao, original.solicitante_identificacao)
  assert.equal(corpo.dieta_id, 2)
  assert.deepEqual(corpo.dados_dinamicos, { para: 'Acompanhante', cardapio: 'GERAL' })
})

test('nenhum destino envia prescrição ou valores vazios que apaguem dados anteriores', () => {
  for (const para of ['Paciente', 'Acompanhante', 'Paciente e Acompanhante']) {
    const corpo = corpoPedido({ para, leito: '102' }, original)
    assert.equal(Object.hasOwn(corpo, 'prescricao'), false)
    assert.equal(corpo.leito, '102')
    assert.equal(corpo.dieta_id, original.dieta_id)
  }
  assert.deepEqual(original.prescricao, { referencia: 'Referência anterior' })
})

test('pedido sem referência anterior pode ser corrigido sem criar dados de prescrição', () => {
  const corpo = corpoPedido({ nome_paciente: 'Pessoa fictícia', dieta_id: '1' }, { ...original, prescricao: null })
  assert.equal(Object.hasOwn(corpo, 'prescricao'), false)
  assert.equal(corpo.nome_paciente, 'Pessoa fictícia')
  assert.equal(corpo.dieta_id, 1)
})
