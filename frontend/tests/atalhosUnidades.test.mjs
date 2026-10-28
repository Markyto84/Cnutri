import assert from 'node:assert/strict'
import test from 'node:test'
import { criarAtalhoUnidade } from '../src/services/atalhosUnidades.js'

const unidade = { id: 3, nome: 'Hospital Colorado', codigo_slug: 'unidade-colorado', ativa: true }
const lerDownload = atalho => Buffer.from(atalho.href.slice(atalho.href.indexOf(',') + 1), 'base64')
const lerAtalho = atalho => {
  const zip = lerDownload(atalho)
  const inicio = 30 + zip.readUInt16LE(26) + zip.readUInt16LE(28)
  return zip.subarray(inicio, inicio + zip.readUInt32LE(22))
}
const textoAtalho = atalho => lerAtalho(atalho).toString('utf16le')

for (const origem of ['http://10.1.140.15:5173', 'https://cnutri.empresa.local']) {
  test(`atalho distribuído abre diretamente a unidade usando ${origem}`, () => {
    const atalho = criarAtalhoUnidade(unidade, origem)
    assert.equal(atalho.url, origem + '/unidade-colorado')
    assert.equal(atalho.nomeArquivo, 'Cnutri - unidade-colorado.zip')
    assert.equal(atalho.nomeAtalho, 'Cnutri - unidade-colorado.lnk')
    assert.equal(atalho.tipoMime, 'application/zip')
    assert.ok(lerAtalho(atalho).includes(Buffer.from(`"${origem}/unidade-colorado"`, 'utf16le')))
    assert.deepEqual(Buffer.from(atalho.conteudo), lerDownload(atalho))
  })
}

test('edição do endereço salva um atalho novo sem incluir sessão ou parâmetros da administração', () => {
  const anterior = criarAtalhoUnidade(unidade, 'https://cnutri.empresa.local/admin?token=nao-compartilhar#unidades')
  const atualizado = criarAtalhoUnidade({ ...unidade, codigo_slug: 'unidade-colorado-nova' }, 'https://cnutri.empresa.local')
  assert.equal(anterior.url, 'https://cnutri.empresa.local/unidade-colorado')
  assert.equal(atualizado.url, 'https://cnutri.empresa.local/unidade-colorado-nova')
  assert.equal(atualizado.nomeArquivo, 'Cnutri - unidade-colorado-nova.zip')
  assert.doesNotMatch(textoAtalho(anterior), /admin|token|nao-compartilhar|#|\?/)
})

test('não gera download para rascunho, unidade inativa ou endereço inválido', () => {
  for (const dados of [null, { codigo_slug: 'a', ativa: true }, { ...unidade, ativa: false },
    { ...unidade, codigo_slug: 'a\r\nURL=https://externo.invalid' }, { ...unidade, codigo_slug: '../admin' }]) {
    assert.equal(criarAtalhoUnidade(dados, 'http://10.1.140.15:5173'), null)
  }
  for (const origem of ['invalida', 'javascript:alert(1)', 'file:///tmp/']) assert.equal(criarAtalhoUnidade(unidade, origem), null)
})

test('atalho usa o servidor da instalação mesmo quando a TI acessa por localhost', () => {
  const atalho = criarAtalhoUnidade(unidade, 'http://localhost:5173/admin', 'https://ceres.exemplo.local:8443')
  assert.equal(atalho.url, 'https://ceres.exemplo.local:8443/unidade-colorado')
  assert.ok(lerAtalho(atalho).includes(Buffer.from('"https://ceres.exemplo.local:8443/unidade-colorado"', 'utf16le')))
})

test('atalho nativo delega a URL ao Windows sem fixar navegador, unidade de disco ou credenciais', () => {
  const atalho = criarAtalhoUnidade({ ...unidade, nome: 'Hospital São João · Havaí' }, 'http://10.1.140.15:5173')
  const bytes = lerAtalho(atalho)
  assert.equal(bytes.readUInt32LE(0), 0x4c)
  assert.equal(bytes.subarray(4, 20).toString('hex'), '0114020000000000c000000000000046')
  assert.ok(bytes.includes(Buffer.from('%SystemRoot%\\explorer.exe', 'utf16le')))
  assert.ok(bytes.includes(Buffer.from('Hospital São João · Havaí', 'utf16le')))
  assert.doesNotMatch(textoAtalho(atalho), /chrome\.exe|msedge\.exe|firefox\.exe|cmd\.exe|powershell|C:\\Users\\|access_token/i)
  assert.deepEqual([...bytes.subarray(-4)], [0, 0, 0, 0])
})

test('endereço configurado inválido não distribui um atalho para outro destino', () => {
  for (const endereco of ['javascript:alert(1)', 'https://usuario:senha@ceres.exemplo.local', 'https://ceres.exemplo.local/admin', 'https://ceres.exemplo.local?token=teste']) {
    assert.equal(criarAtalhoUnidade(unidade, 'http://localhost:5173', endereco), null)
  }
})
