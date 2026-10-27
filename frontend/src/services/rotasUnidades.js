/** Usa o identificador já cadastrado, sem alterar nomes ou IDs das unidades. */
export function caminhoCozinha(filial) {
  const referencia = filial?.codigo_slug || filial?.id
  return referencia ? `/cozinha/${encodeURIComponent(referencia)}` : null
}

export function unidadeDoPainel(pathname, filiais = []) {
  const partes = pathname.match(/^\/(cozinha|entregas)\/([a-z0-9]+(?:-[a-z0-9]+)*)\/?$/)
  if (!partes) return null
  const [, modo, referencia] = partes
  const porNome = modo === 'cozinha' && !/^\d+$/.test(referencia)
  return filiais.find((f) => f.ativa && (porNome ? f.codigo_slug === referencia : String(f.id) === referencia)) || null
}

export function filialDoPlantao(pathname, filiais = []) {
  if (/^\/(cozinha|entregas)\//.test(pathname)) return unidadeDoPainel(pathname, filiais)?.id
  return filiais.find((f) => f.ativa)?.id
}
