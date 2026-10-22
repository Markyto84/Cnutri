import assert from 'node:assert/strict'
import test from 'node:test'
import { ajustarValores, campoVisivel, dietasDisponiveis, erroAcompanhante, opcoesCardapio } from '../src/services/formularioPaciente.js'

const dietas = [{ id: 1, nome: 'GERAL' }, { id: 2, nome: 'PASTOSA' }, { id: 3, nome: 'BRANDA' }]
const grupos = [{ dietas: ['GERAL', 'BRANDA'], opcoes: ['ARROZ E FRANGO', 'CARNE ASSADA'] }, { dietas: ['PASTOSA'], opcoes: ['SOPA CREME'] }]
const cardapio = { id: 'cardapio', tipo: 'cardapio', grupos }
const acompanhante = { id: 'cardapio_acompanhante', tipo: 'cardapio', grupos, dieta_fixa: 'GERAL',
  exibir_quando: { campo: 'para', valor: 'PACIENTE E ACOMPANHANTE' } }
const campos = [cardapio, acompanhante]

test('Paciente conserva todas as dietas e o cardápio da dieta escolhida', () => {
  const valores = { para: 'Paciente', dieta_id: 2, cardapio: 'SOPA CREME', nome_paciente: 'Pessoa fictícia' }
  assert.deepEqual(ajustarValores(campos, dietas, valores), valores)
  assert.deepEqual(dietasDisponiveis(campos, dietas, valores), dietas)
  assert.deepEqual(opcoesCardapio(cardapio, 'PASTOSA'), ['SOPA CREME'])
  assert.equal(campoVisivel(acompanhante, valores), false)
})

test('Acompanhante restringe e seleciona GERAL e limpa cardápio incompatível', () => {
  const valores = ajustarValores(campos, dietas, { para: 'Acompanhante', dieta_id: 2, cardapio: 'SOPA CREME' })
  assert.equal(valores.dieta_id, 1)
  assert.equal(valores.cardapio, '')
  assert.deepEqual(dietasDisponiveis(campos, dietas, valores), [dietas[0]])
  assert.equal(campoVisivel(acompanhante, valores), false)
})

test('Ambos mantém cardápios independentes e a troca de dieta afeta somente o paciente', () => {
  const valores = { para: 'Paciente e Acompanhante', dieta_id: 2, cardapio: 'SOPA CREME', cardapio_acompanhante: 'ARROZ E FRANGO' }
  assert.equal(campoVisivel(acompanhante, valores), true)
  assert.deepEqual(opcoesCardapio(acompanhante, 'PASTOSA'), ['ARROZ E FRANGO', 'CARNE ASSADA'])
  assert.deepEqual(ajustarValores(campos, dietas, valores), valores)
  const novos = ajustarValores(campos, dietas, { ...valores, dieta_id: 3 })
  assert.equal(novos.cardapio, '')
  assert.equal(novos.cardapio_acompanhante, 'ARROZ E FRANGO')
})

test('Voltar de Ambos para Paciente ou Acompanhante remove o campo oculto do envio', () => {
  for (const para of ['Paciente', 'Acompanhante']) {
    const valores = ajustarValores(campos, dietas, { para, dieta_id: 2, cardapio: 'SOPA CREME', cardapio_acompanhante: 'ARROZ E FRANGO' })
    assert.equal('cardapio_acompanhante' in valores, false)
  }
})

test('Sem GERAL ativa ou sem opções, informa o cadastro necessário somente para acompanhante', () => {
  assert.match(erroAcompanhante(campos, dietas.slice(1), { para: 'Acompanhante' }), /precisa estar ativa/)
  assert.match(erroAcompanhante([{ ...acompanhante, grupos: [] }], dietas, { para: 'Paciente e Acompanhante' }), /precisa ser configurado/)
  assert.equal(erroAcompanhante(campos, [], { para: 'Paciente' }), '')
  assert.equal(erroAcompanhante(campos, dietas, { para: 'Paciente e Acompanhante' }), '')
})

test('Formulários sem regra do acompanhante preservam seu comportamento', () => {
  const valores = { para: 'Acompanhante', dieta_id: 2, cardapio: 'SOPA CREME' }
  assert.deepEqual(ajustarValores([cardapio], dietas, valores), valores)
  assert.deepEqual(dietasDisponiveis([cardapio], dietas, valores), dietas)
})
