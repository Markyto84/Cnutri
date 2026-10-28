import assert from 'node:assert/strict'
import test from 'node:test'
import { destinoAposLogin, inicioDoUsuario, podeOperar } from '../src/context/auth.js'

const copeira = { perfil: 'COPEIRA', filiais: [{ id: 1, ativa: true }, { id: 2, ativa: false }] }
const parametros = (retorno) => new URLSearchParams({ retorno })

test('operações exigem perfil, vínculo ativo e senha definitiva', () => {
  assert.equal(podeOperar(null, 1, ['COPEIRA']), false)
  assert.equal(podeOperar(copeira, 1, ['COPEIRA']), true)
  assert.equal(podeOperar(copeira, 2, ['COPEIRA']), false)
  assert.equal(podeOperar(copeira, 1, ['COZINHA']), false)
  assert.equal(podeOperar({ ...copeira, troca_senha_obrigatoria: true }, 1, ['COPEIRA']), false)
})

test('login retorna ao painel autorizado após abrir pelo dashboard público', () => {
  assert.equal(destinoAposLogin(copeira, parametros('/entregas/1')), '/entregas/1')
  assert.equal(destinoAposLogin({ perfil: 'ADMIN_TI' }, parametros('/cozinha/2')), '/cozinha/2')
})

test('redirecionamentos externos ou fora das unidades e do perfil são descartados', () => {
  for (const retorno of ['https://externo.test', '//externo.test', '/entregas/2', '/entregas/3', '/cozinha/1', '/entregas/1?url=externo', '/entregas/1/../admin']) {
    assert.equal(destinoAposLogin(copeira, parametros(retorno)), '/entregas/1')
  }
})

test('troca obrigatória vem antes do painel e preserva retorno interno permitido', () => {
  const usuario = { ...copeira, troca_senha_obrigatoria: true }
  assert.equal(inicioDoUsuario(usuario), '/senha')
  assert.equal(destinoAposLogin(usuario, parametros('/entregas/1')), '/senha?retorno=%2Fentregas%2F1')
})

test('login no celular retorna ao QR Code e preserva troca obrigatória de senha', () => {
  assert.equal(destinoAposLogin(copeira, parametros('/receber')), '/receber')
  assert.equal(destinoAposLogin({ ...copeira, troca_senha_obrigatoria: true }, parametros('/receber')), '/senha?retorno=%2Freceber')
  assert.equal(destinoAposLogin(copeira, parametros('/receber?codigo=indevido')), '/entregas/1')
})
