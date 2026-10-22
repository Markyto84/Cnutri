/** As opções do acompanhante usam o mesmo grupo GERAL publicado pela Gestão. */
export const normalizarNome = (valor) => typeof valor === 'string' ? valor.normalize('NFC').trim().toUpperCase() : ''

export function campoVisivel(campo, valores) {
  const condicao = campo.exibir_quando
  return !condicao || normalizarNome(valores[condicao.campo]) === normalizarNome(condicao.valor)
}

export function opcoesCardapio(campo, dietaNome) {
  const nome = normalizarNome(campo.dieta_fixa ?? dietaNome)
  return (campo.grupos || []).find((g) => nome && (g.dietas || []).some((d) => normalizarNome(d) === nome))?.opcoes || []
}

const temRegra = (campos) => campos.some((c) => c.id === 'cardapio_acompanhante' && c.dieta_fixa === 'GERAL')
const incluiAcompanhante = (valores) => ['ACOMPANHANTE', 'PACIENTE E ACOMPANHANTE'].includes(normalizarNome(valores.para))

export function dietasDisponiveis(campos, dietas, valores) {
  return temRegra(campos) && normalizarNome(valores.para) === 'ACOMPANHANTE'
    ? dietas.filter((d) => normalizarNome(d.nome) === 'GERAL') : dietas
}

export function ajustarValores(campos, dietas, valores) {
  const novos = { ...valores }
  if (temRegra(campos) && normalizarNome(novos.para) === 'ACOMPANHANTE') {
    novos.dieta_id = dietasDisponiveis(campos, dietas, novos)[0]?.id ?? ''
  }
  const nome = dietas.find((d) => d.id === Number(novos.dieta_id))?.nome || ''
  for (const campo of campos.filter((c) => c.tipo === 'cardapio')) {
    if (!campoVisivel(campo, novos)) delete novos[campo.id]
    else if (novos[campo.id] && !opcoesCardapio(campo, nome).includes(novos[campo.id])) novos[campo.id] = ''
  }
  return novos
}

export function erroAcompanhante(campos, dietas, valores) {
  if (!temRegra(campos) || !incluiAcompanhante(valores)) return ''
  if (!dietas.some((d) => normalizarNome(d.nome) === 'GERAL')) return 'A dieta GERAL precisa estar ativa nesta unidade. Solicite o cadastro à Nutrição.'
  const campo = campos.find((c) => c.id === 'cardapio_acompanhante')
  return opcoesCardapio(campo, 'GERAL').length ? '' : 'O cardápio da dieta GERAL precisa ser configurado pela Nutrição para o acompanhante.'
}
