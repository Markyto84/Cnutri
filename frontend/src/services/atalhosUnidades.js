/** O atalho usa a unidade salva e o endereço pelo qual a TI acessou o sistema. */
export function criarAtalhoUnidade(filial, origem) {
  const codigo = filial?.codigo_slug
  if (!Number.isSafeInteger(filial?.id) || filial.id <= 0 || !filial.ativa
    || typeof codigo !== 'string' || codigo.length > 50 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(codigo)) return null

  let base
  try { base = new URL(origem) } catch { return null }
  if (!['http:', 'https:'].includes(base.protocol)) return null
  const url = new URL(`/${encodeURIComponent(codigo)}`, base.origin).href
  const conteudo = `[InternetShortcut]\r\nURL=${url}\r\n`
  return {
    url,
    nomeArquivo: `Cnutri - ${codigo}.url`,
    conteudo,
    href: `data:application/octet-stream;charset=utf-8,${encodeURIComponent(conteudo)}`,
  }
}
