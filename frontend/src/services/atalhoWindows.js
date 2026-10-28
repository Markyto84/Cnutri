// Formato MS-SHLLINK: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-shllink/
// O Explorer encaminha a URL ao navegador padrão do Windows do destinatário.
// O arquivo é gerado no navegador; o servidor pode continuar rodando em Linux.
const DESTINO = '%SystemRoot%\\explorer.exe'
const ICONE = '%SystemRoot%\\System32\\url.dll'

function textoUnicode(texto, tamanho = texto.length * 2) {
  const bytes = new Uint8Array(tamanho)
  const view = new DataView(bytes.buffer)
  for (let i = 0; i < texto.length; i++) view.setUint16(i * 2, texto.charCodeAt(i), true)
  return bytes
}

function stringData(texto) {
  const bytes = new Uint8Array(2 + texto.length * 2)
  new DataView(bytes.buffer).setUint16(0, texto.length, true)
  bytes.set(textoUnicode(texto), 2)
  return bytes
}

function blocoAmbiente(assinatura, caminho) {
  const bytes = new Uint8Array(0x314)
  const view = new DataView(bytes.buffer)
  view.setUint32(0, bytes.length, true)
  view.setUint32(4, assinatura, true)
  for (let i = 0; i < caminho.length; i++) bytes[8 + i] = caminho.charCodeAt(i)
  bytes.set(textoUnicode(caminho, 520), 268)
  return bytes
}

export function criarAtalhoWindows(url, descricao) {
  let endereco
  try { endereco = new URL(url) } catch { return null }
  if (!['http:', 'https:'].includes(endereco.protocol) || endereco.username || endereco.password
    || endereco.search || endereco.hash || endereco.href !== url) return null
  const nome = Array.from(String(descricao)).filter(c => c.codePointAt(0) >= 32 && c.codePointAt(0) !== 127).join('').slice(0, 240)
  const cabecalho = new Uint8Array(76)
  const view = new DataView(cabecalho.buffer)
  view.setUint32(0, 0x4c, true)
  cabecalho.set([0x01, 0x14, 0x02, 0, 0, 0, 0, 0, 0xc0, 0, 0, 0, 0, 0, 0, 0x46], 4)
  // Nome, argumentos, ícone, Unicode, destino/ícone por variáveis de ambiente.
  view.setUint32(20, 0x020042e4, true)
  view.setUint32(24, 0x20, true)
  view.setUint32(60, 1, true)
  const partes = [cabecalho, stringData(nome), stringData(`"${url}"`), stringData(ICONE),
    blocoAmbiente(0xa0000001, DESTINO), blocoAmbiente(0xa0000007, ICONE), new Uint8Array(4)]
  const arquivo = new Uint8Array(partes.reduce((total, parte) => total + parte.length, 0))
  let posicao = 0
  for (const parte of partes) { arquivo.set(parte, posicao); posicao += parte.length }
  return arquivo
}
