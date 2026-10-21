import assert from 'node:assert/strict'
import test from 'node:test'
import { MAX_SENHA, MIN_SENHA, PADRAO_SENHA, senhaValida } from '../src/services/politicaSenha.js'

test('senhas novas aceitam os limites de oito e doze e rejeitam sete e treze', () => {
  assert.equal(MIN_SENHA, 8)
  assert.equal(MAX_SENHA, 12)
  assert.equal(senhaValida('Teste1!?'), true)
  assert.equal(senhaValida('NovaSenha12!'), true)
  assert.equal(senhaValida('Ab1!xyz'), false)
  assert.equal(senhaValida('Ab1!abcdefghi'), false)
})

test('maiúscula, número e símbolo são exigidos e espaço não conta como símbolo', () => {
  for (const senha of ['abcdef1!', 'Abcdefg1', 'ABCDEF!@', 'Teste12 ', 'Téste123']) assert.equal(senhaValida(senha), false)
})

test('não exige minúscula e reconhece maiúsculas acentuadas também no padrão HTML', () => {
  const padrao = new RegExp(`^(?:${PADRAO_SENHA})$`, 'v')
  for (const senha of ['TESTE1!?', 'Ábcdef1!', 'Teste1!?']) {
    assert.equal(senhaValida(senha), true)
    assert.equal(padrao.test(senha), true)
  }
  for (const senha of ['abcdef1!', 'Abcdefg1', 'ABCDEF!@', 'Teste12 ']) assert.equal(padrao.test(senha), false)
})
