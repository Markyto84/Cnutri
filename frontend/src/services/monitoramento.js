export function estadoSondas(saude, prontidao) {
  return {
    api: saude.status === 'fulfilled' && saude.value.status === 200 ? 'RESPONDENDO' : 'INDISPONIVEL',
    banco: prontidao.status === 'fulfilled' && prontidao.value.status === 200 ? 'CONECTADO'
      : prontidao.status === 'rejected' && prontidao.reason.response?.status === 503 ? 'INDISPONIVEL' : 'DESCONHECIDO',
  }
}

export function tamanhoLegivel(valor) {
  if (!Number.isFinite(valor) || valor < 0) return 'Não informado'
  if (valor < 1024 * 1024) return `${(valor / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} KiB`
  if (valor < 1024 ** 3) return `${(valor / 1024 ** 2).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MiB`
  return `${(valor / 1024 ** 3).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} GiB`
}

export function tempoAtivo(segundos) {
  if (!Number.isFinite(segundos) || segundos < 0) return 'Não informado'
  return `${Math.floor(segundos / 86400)}d ${Math.floor(segundos % 86400 / 3600)}h ${Math.floor(segundos % 3600 / 60)}min`
}
