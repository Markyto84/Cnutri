import test from 'node:test'
import assert from 'node:assert/strict'
import { corpoConfiguracaoEmail, enderecoAdminLocal, escolherModeloEmail, formularioEmail } from '../src/services/configuracaoEmail.js'

test('SMTP personalizado conserva usuário separado, senha do ambiente e parâmetros de entrega', () => {
  const form = { ...formularioEmail(), remetente: 'dietas@example.com', usuario: 'servico', senha_app: ' Exemplo!2026 ',
    servidor: 'smtp.local', porta: '465', seguranca: 'TLS', servidor_secundario: 'reserva.local', porta_secundaria: '465', endereco_resposta: 'nutricao@example.com' }
  const dados = corpoConfiguracaoEmail(form)
  assert.equal(dados.usuario, 'servico'); assert.equal(dados.senha, ' Exemplo!2026 ')
  assert.equal(dados.porta, 465); assert.equal(dados.porta_secundaria, 465)
  assert.equal(dados.endereco_resposta, 'nutricao@example.com')
})
test('relay sem autenticação omite senha e usuário mesmo se houver valor anterior', () => {
  const dados = corpoConfiguracaoEmail({ ...formularioEmail(), autenticar: false, usuario: 'anterior', senha_app: 'nao-enviar' })
  assert.equal(dados.usuario, null); assert.equal(Object.hasOwn(dados, 'senha'), false)
  assert.equal(dados.servidor_secundario, null); assert.equal(dados.porta_secundaria, null)
})
test('trocar modelo limpa a credencial anterior e conserva a configuração da unidade', () => {
  const form = { ...formularioEmail(), remetente: 'dietas@example.com', senha_app: 'anterior' }
  const google = escolherModeloEmail(form, 'GOOGLE_APP')
  assert.equal(google.servidor, 'smtp.gmail.com'); assert.equal(google.senha_app, '')
  assert.equal(google.usuario, form.remetente)
  assert.equal(escolherModeloEmail(form, 'GOOGLE_RELAY').autenticar, false)
})
test('acesso local acompanha a porta da instalação e remove parâmetros', () => {
  assert.equal(enderecoAdminLocal('http://192.0.2.10:8080/gestao?x=1#antigo'), 'http://127.0.0.1:8080/admin')
})
