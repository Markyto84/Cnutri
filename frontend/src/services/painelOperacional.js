export const FILTROS_VAZIOS = { busca: '', andar: '', leito: '', tipo: '', refeicao: '' }

export function normalizarBusca(valor) {
  return String(valor ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').trim()
}

export function filtrarPedidos(pedidos, filtros) {
  const busca = normalizarBusca(filtros.busca).replace(/^#/, '')
  return pedidos.filter((p) => {
    const d = p.dados_dinamicos || {}
    return (!filtros.andar || d.andar === filtros.andar)
      && (!filtros.leito || p.leito === filtros.leito)
      && (!filtros.tipo || p.tipo_solicitacao === filtros.tipo)
      && (!filtros.refeicao || d.refeicao === filtros.refeicao)
      && (!busca || [p.id, p.leito, p.nome_paciente, p.solicitante_nome].some((v) => normalizarBusca(v).includes(busca)))
  })
}

export function atrasoPedido(pedido, limites, agora = Date.now()) {
  const entrega = pedido.status === 'PRONTO'
  if (!entrega && !['PENDENTE', 'EM_PREPARO'].includes(pedido.status)) return null
  const limite = entrega ? limites?.entrega_minutos : limites?.preparo_minutos
  const data = entrega ? pedido.concluido_em : pedido.criado_em
  if (!Number.isInteger(limite) || limite <= 0 || !data) return null
  const inicio = Date.parse(/(?:Z|[+-]\d\d:\d\d)$/i.test(data) ? data : `${data}Z`)
  const decorrido = (agora - inicio) / 60000
  if (!Number.isFinite(decorrido) || decorrido < limite) return null
  return { etapa: entrega ? 'Entrega' : 'Preparo', minutos: Math.floor(decorrido), limite }
}

export function dataBrasilia(valor = new Date()) {
  return new Date(valor).toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' })
}

export function horarioBrasilia(valor) {
  return valor ? new Date(valor).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }) : '—'
}

export function mensagemErro(erro) {
  const d = erro.response?.data?.detail
  return Array.isArray(d) ? d.map((item) => item.msg.replace(/^Value error, /, '')).join('. ')
    : typeof d === 'string' ? d : 'Não foi possível concluir. Tente atualizar a página.'
}
