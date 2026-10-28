import { MARCA } from './marca.js'

/** A instalação define o destino; versões anteriores usam o endereço aberto pela TI. */
export function criarAtalhoUnidade(filial, origem, enderecoPublico = null) {
  const codigo = filial?.codigo_slug
  if (!Number.isSafeInteger(filial?.id) || filial.id <= 0 || !filial.ativa
    || typeof codigo !== 'string' || codigo.length > 50 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(codigo)) return null

  let base
  try { base = new URL(enderecoPublico || origem) } catch { return null }
  if (!['http:', 'https:'].includes(base.protocol)) return null
  if (enderecoPublico && (base.username || base.password || !['', '/'].includes(base.pathname) || base.search || base.hash)) return null
  const url = new URL(`/${encodeURIComponent(codigo)}`, base.origin).href
  const conteudo = `[InternetShortcut]\r\nURL=${url}\r\n`
  return {
    url,
    nomeArquivo: `${MARCA.nome} - ${codigo}.url`,
    conteudo,
    href: `data:application/octet-stream;charset=utf-8,${encodeURIComponent(conteudo)}`,
  }
}
