const CHAVE = 'cnutri-retirada-apos-login'
const VALIDADE_MS = 5 * 60 * 1000

export function etapaEntrega(pedido) {
  return pedido.status === 'PRONTO' && (pedido.retirada || pedido.em_entrega) ? 'EM_ENTREGA' : pedido.status
}

export function guardarRetirada(filialId, pedidoId, armazenamento = sessionStorage, agora = Date.now()) {
  armazenamento.setItem(CHAVE, JSON.stringify({ filialId: Number(filialId), pedidoId: Number(pedidoId), criadoEm: agora }))
}

export function consumirRetirada(filialId, armazenamento = sessionStorage, agora = Date.now()) {
  const valor = armazenamento.getItem(CHAVE)
  if (!valor) return null
  armazenamento.removeItem(CHAVE)
  try {
    const pendente = JSON.parse(valor)
    return Number.isSafeInteger(pendente.pedidoId) && pendente.pedidoId > 0 && pendente.filialId === Number(filialId)
      && Number.isFinite(pendente.criadoEm) && agora >= pendente.criadoEm && agora - pendente.criadoEm < VALIDADE_MS ? pendente.pedidoId : null
  } catch { return null }
}

export function limparRetirada(armazenamento = sessionStorage) {
  armazenamento.removeItem(CHAVE)
}
