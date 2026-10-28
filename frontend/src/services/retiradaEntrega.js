const CHAVE = 'cnutri-retirada-apos-login'

export function etapaEntrega(pedido) {
  return pedido.status === 'PRONTO' && (pedido.retirada || pedido.em_entrega) ? 'EM_ENTREGA' : pedido.status
}

// Limpa intenções deixadas por versões anteriores do painel.
export function limparRetirada(armazenamento = sessionStorage) {
  armazenamento.removeItem(CHAVE)
}
