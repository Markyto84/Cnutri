// ZIP sem compressão, com um arquivo UTF-8. Sem dependências ou código executável.
// Especificação: https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
export function empacotarArquivoZip(nome, dados) {
  if (!nome || nome.includes('/') || nome.includes('\\') || nome.includes('\0') || nome === '.' || nome === '..') return null
  const nomeBytes = new TextEncoder().encode(nome)
  if (nomeBytes.length > 65535) return null
  let crc = 0xffffffff
  for (const byte of dados) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0)
  }
  crc = (crc ^ 0xffffffff) >>> 0
  const local = new Uint8Array(30 + nomeBytes.length)
  const central = new Uint8Array(46 + nomeBytes.length)
  const fim = new Uint8Array(22)
  const l = new DataView(local.buffer), c = new DataView(central.buffer), f = new DataView(fim.buffer)
  l.setUint32(0, 0x04034b50, true); l.setUint16(4, 20, true); l.setUint16(6, 0x0800, true)
  l.setUint16(12, 33, true); l.setUint32(14, crc, true)
  l.setUint32(18, dados.length, true); l.setUint32(22, dados.length, true); l.setUint16(26, nomeBytes.length, true)
  local.set(nomeBytes, 30)
  c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true)
  c.setUint16(14, 33, true); c.setUint32(16, crc, true)
  c.setUint32(20, dados.length, true); c.setUint32(24, dados.length, true); c.setUint16(28, nomeBytes.length, true)
  c.setUint32(38, 0x20, true)
  central.set(nomeBytes, 46)
  f.setUint32(0, 0x06054b50, true); f.setUint16(8, 1, true); f.setUint16(10, 1, true)
  f.setUint32(12, central.length, true); f.setUint32(16, local.length + dados.length, true)
  const resultado = new Uint8Array(local.length + dados.length + central.length + fim.length)
  let posicao = 0
  for (const parte of [local, dados, central, fim]) { resultado.set(parte, posicao); posicao += parte.length }
  return resultado
}
