import assert from 'node:assert/strict'
import test from 'node:test'
import { corpoPedido, exigeReferencia, horarioLocalPrescricao, referenciaPayload } from '../src/services/prescricao.js'

test('referência obrigatória para paciente e ambos; acompanhante e equipe conservam fluxo próprio', () => {
  assert.equal(exigeReferencia('MEDICO', {}), false)
  assert.equal(exigeReferencia('PACIENTE', { para: 'Acompanhante' }), false)
  assert.equal(exigeReferencia('PACIENTE', { para: 'Paciente e Acompanhante' }), true)
  assert.equal(exigeReferencia('ENFERMAGEM', {}), true)
})

test('data do prontuário usa Brasília e transporta fuso explícito', () => {
  const local = horarioLocalPrescricao('2026-10-26T02:15:00+00:00')
  assert.equal(local, '2026-10-25T23:15')
  const p = referenciaPayload({ referencia: ' Ref. 1 ', data_hora: local, prescritor_nome: ' Ana ', prescritor_registro: ' CRN TESTE ' })
  assert.equal(p.data_hora, '2026-10-25T23:15:00-03:00')
  assert.equal(p.referencia, 'Ref. 1')
  assert.equal(new Date(p.data_hora).toISOString(), '2026-10-26T02:15:00.000Z')
  const segundos = horarioLocalPrescricao('2026-10-26T02:15:42Z')
  assert.equal(segundos, '2026-10-25T23:15:42')
  assert.equal(referenciaPayload({ data_hora: segundos }).data_hora, '2026-10-25T23:15:42-03:00')
})

test('correção mantém solicitante original separado do autor e remove referência no acompanhante', () => {
  const original = { tipo_solicitacao: 'PACIENTE', solicitante_nome: 'Solicitante original', solicitante_identificacao: 'COREN TESTE' }
  const corpo = corpoPedido({ nome_paciente: 'Paciente teste', dieta_id: '2', para: 'Acompanhante', cardapio: 'GERAL' }, original, {})
  assert.equal(corpo.solicitante_nome, original.solicitante_nome)
  assert.equal(corpo.dieta_id, 2)
  assert.deepEqual(corpo.dados_dinamicos, { para: 'Acompanhante', cardapio: 'GERAL' })
  assert.equal(corpo.prescricao, null)
})
