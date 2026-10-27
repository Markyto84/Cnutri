import assert from 'node:assert/strict'
import test from 'node:test'
import { caminhoCozinha, filialDoPlantao, unidadeDoPainel } from '../src/services/rotasUnidades.js'
import { destinoAposLogin, inicioDoUsuario } from '../src/context/auth.js'

const filiais = [
  { id: 1, nome: 'Hospital Havaí', codigo_slug: 'unidade-havai', ativa: true },
  { id: 2, nome: 'Hospital Dubai', codigo_slug: 'unidade-dubai', ativa: true },
  { id: 3, nome: 'Hospital Colorado', codigo_slug: 'unidade-colorado', ativa: false },
]
const cozinha = { perfil: 'COZINHA', filiais }
const retorno = (path) => new URLSearchParams({ retorno: path })

test('links usam o identificador cadastrado e preservam títulos e IDs', () => {
  assert.equal(caminhoCozinha(filiais[0]), '/cozinha/unidade-havai')
  assert.equal(caminhoCozinha({ ...filiais[1], nome: filiais[0].nome }), '/cozinha/unidade-dubai')
  assert.equal(caminhoCozinha({ id: 1 }), '/cozinha/1')
  assert.equal(caminhoCozinha(undefined), null)
})

test('presença usa a unidade da URL por nome, sem cair silenciosamente na primeira unidade', () => {
  assert.equal(filialDoPlantao('/cozinha/unidade-dubai', filiais), 2)
  assert.equal(filialDoPlantao('/cozinha/2', filiais), 2)
  assert.equal(filialDoPlantao('/entregas/2', filiais), 2)
  assert.equal(filialDoPlantao('/cozinha/unidade-colorado', filiais), undefined)
  assert.equal(filialDoPlantao('/cozinha/sem-vinculo', filiais), undefined)
  assert.equal(filialDoPlantao('/entregas/unidade-dubai', filiais), undefined)
  assert.equal(filialDoPlantao('/gestao', filiais), 1)
  assert.equal(unidadeDoPainel('/cozinha/unidade-dubai/', filiais)?.id, 2)
})

test('início da cozinha e retorno do login/senha usam o nome mantendo permissões', () => {
  assert.equal(inicioDoUsuario(cozinha), '/cozinha/unidade-havai')
  assert.equal(destinoAposLogin(cozinha, retorno('/cozinha/unidade-dubai')), '/cozinha/unidade-dubai')
  assert.equal(destinoAposLogin(cozinha, retorno('/cozinha/2')), '/cozinha/unidade-dubai')
  assert.equal(destinoAposLogin({ ...cozinha, troca_senha_obrigatoria: true }, retorno('/cozinha/unidade-dubai')), '/senha?retorno=%2Fcozinha%2Funidade-dubai')
  assert.equal(destinoAposLogin({ perfil: 'ADMIN_TI' }, retorno('/cozinha/unidade-dubai')), '/cozinha/unidade-dubai')
  assert.equal(destinoAposLogin({ perfil: 'COPEIRA', filiais }, retorno('/cozinha/unidade-dubai')), '/entregas/1')
})

test('nomes de unidades não permitem redirecionamento externo nem retorno sem vínculo', () => {
  for (const path of ['https://externo.test', '//externo.test', '/cozinha/../admin', '/cozinha/%2fadmin',
    '/cozinha/unidade-dubai?url=externo', '/cozinha/unidade-colorado', '/cozinha/sem-vinculo', '/entregas/unidade-dubai']) {
    assert.equal(destinoAposLogin(cozinha, retorno(path)), '/cozinha/unidade-havai')
  }
})
