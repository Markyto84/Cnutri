// Contrato v1; a compatibilidade com o backend é conferida nos testes do módulo.
export const CONTRATO_ASSINATURA = Object.freeze({
  versao: 1, maxTracos: 40, minPontosTraco: 2, maxPontosTraco: 1500,
  maxPontos: 8000, minComprimento: 0.08, largura: 1000, altura: 500, espessura: 6,
})

export function totalPontos(tracos) {
  return tracos.reduce((n, traco) => n + traco.length, 0)
}

export function validarAssinatura(tracos) {
  const c = CONTRATO_ASSINATURA
  if (!Array.isArray(tracos) || !tracos.length) return 'Desenhe a assinatura no campo indicado.'
  if (tracos.length > c.maxTracos) return 'Limite de traços atingido. Limpe o campo e assine novamente.'
  let pontos = 0, comprimento = 0
  for (const traco of tracos) {
    if (!Array.isArray(traco) || traco.length < c.minPontosTraco) return 'Desenhe a assinatura no campo indicado.'
    if (traco.length > c.maxPontosTraco) return 'Traço muito extenso. Limpe o campo e assine novamente.'
    pontos += traco.length
    if (pontos > c.maxPontos) return 'Assinatura muito extensa. Limpe o campo e assine novamente.'
    for (let i = 0; i < traco.length; i++) {
      const p = traco[i]
      if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) {
        return 'A assinatura contém um ponto fora da área de desenho.'
      }
      if (i) comprimento += Math.hypot(p.x - traco[i - 1].x, p.y - traco[i - 1].y)
    }
  }
  return comprimento < c.minComprimento ? 'Desenhe a assinatura no campo indicado.' : null
}

export function prepararAssinatura(tracos) {
  const erro = validarAssinatura(tracos)
  if (erro) throw new Error(erro)
  // Um payload independente impede alterações no comprovante durante um envio.
  return { tracos: tracos.map((traco) => traco.map(({ x, y }) => ({ x, y }))) }
}

export function normalizarPonto(clientX, clientY, area) {
  if (![clientX, clientY, area.left, area.top, area.width, area.height].every(Number.isFinite) || area.width <= 0 || area.height <= 0) return null
  const normalizar = (n) => Math.round(Math.min(1, Math.max(0, n)) * 10000) / 10000
  return { x: normalizar((clientX - area.left) / area.width), y: normalizar((clientY - area.top) / area.height) }
}

export function capacidadeNovoTraco(tracos) {
  const c = CONTRATO_ASSINATURA
  if (tracos.length >= c.maxTracos) return 0
  const capacidade = Math.min(c.maxPontosTraco, c.maxPontos - totalPontos(tracos))
  return capacidade < c.minPontosTraco ? 0 : capacidade
}
