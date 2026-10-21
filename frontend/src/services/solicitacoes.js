// Web Crypto getRandomValues também funciona nos links HTTP legados da rede.
export function criarChaveEnvio() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = [...bytes].map((n) => n.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const memoria = new Map()

export function chaveSalva(slug) {
  try { return sessionStorage.getItem(`cnutri-envio:${slug}`) || memoria.get(slug) }
  catch { return memoria.get(slug) }
}

export function obterChaveEnvio(slug) {
  let chave = chaveSalva(slug)
  if (!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(chave || '')) {
    chave = criarChaveEnvio()
    memoria.set(slug, chave)
    try { sessionStorage.setItem(`cnutri-envio:${slug}`, chave) } catch { /* mantém a tentativa enquanto a página estiver aberta */ }
  }
  return chave
}

export function concluirTentativa(slug) {
  memoria.delete(slug)
  try { sessionStorage.removeItem(`cnutri-envio:${slug}`) } catch { /* armazenamento indisponível */ }
}

export function textoImpressao(estado) {
  return ({ PENDENTE: 'Filipeta na fila de impressão', PROCESSANDO: 'Enviando filipeta à impressora',
    ENVIADO: 'Filipeta enviada à impressora', FALHA: 'Impressão não concluída', INCERTO: 'Envio precisa de conferência na cozinha',
    CANCELADO: 'Envio cancelado' })[estado] || 'Impressão sem registro de envio'
}
