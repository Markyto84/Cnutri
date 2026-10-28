import assert from 'node:assert/strict'
import test from 'node:test'
import { criarAtalhoUnidade } from '../src/services/atalhosUnidades.js'

const unidade = { id: 3, nome: 'Hospital Colorado', codigo_slug: 'unidade-colorado', ativa: true }
const lerDownload = (atalho) => decodeURIComponent(atalho.href.slice(atalho.href.indexOf(',') + 1))

for (const origem of ['http://10.1.140.15:5173', 'https://cnutri.empresa.local']) {
  test(`atalho distribuído abre diretamente a unidade usando ${origem}`, () => {
    const atalho = criarAtalhoUnidade(unidade, origem)
    assert.equal(atalho.url, origem + '/unidade-colorado')
    assert.equal(atalho.nomeArquivo, 'Ceres Care - unidade-colorado.url')
    assert.equal(lerDownload(atalho), '[InternetShortcut]\r\nURL=' + origem + '/unidade-colorado\r\n')
    assert.equal(atalho.conteudo, lerDownload(atalho))
  })
}

test('edição do endereço salva um atalho novo sem incluir sessão ou parâmetros da administração', () => {
  const anterior = criarAtalhoUnidade(unidade, 'https://cnutri.empresa.local/admin?token=nao-compartilhar#unidades')
  const atualizado = criarAtalhoUnidade({ ...unidade, codigo_slug: 'unidade-colorado-nova' }, 'https://cnutri.empresa.local')
  assert.equal(anterior.url, 'https://cnutri.empresa.local/unidade-colorado')
  assert.equal(atualizado.url, 'https://cnutri.empresa.local/unidade-colorado-nova')
  assert.equal(atualizado.nomeArquivo, 'Ceres Care - unidade-colorado-nova.url')
  assert.doesNotMatch(lerDownload(anterior), /admin|token|nao-compartilhar|#|\?/)
})

test('não gera download para rascunho, unidade inativa ou endereço inválido', () => {
  for (const dados of [null, { codigo_slug: 'a', ativa: true }, { ...unidade, ativa: false },
    { ...unidade, codigo_slug: 'a\r\nURL=https://externo.invalid' }, { ...unidade, codigo_slug: '../admin' }]) {
    assert.equal(criarAtalhoUnidade(dados, 'http://10.1.140.15:5173'), null)
  }
  for (const origem of ['invalida', 'javascript:alert(1)', 'file:///tmp/']) assert.equal(criarAtalhoUnidade(unidade, origem), null)
})
