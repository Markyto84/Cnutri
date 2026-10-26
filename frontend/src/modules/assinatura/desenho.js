import { CONTRATO_ASSINATURA } from './modelo.js'

export function desenharAssinatura(canvas, tracos) {
  const contexto = canvas?.getContext('2d')
  if (!contexto) return
  contexto.fillStyle = '#ffffff'
  contexto.fillRect(0, 0, canvas.width, canvas.height)
  contexto.strokeStyle = '#141414'
  contexto.lineWidth = CONTRATO_ASSINATURA.espessura
  contexto.lineCap = 'round'
  contexto.lineJoin = 'round'
  for (const traco of tracos) {
    contexto.beginPath()
    traco.forEach((p, i) => {
      const x = p.x * (canvas.width - 1), y = p.y * (canvas.height - 1)
      if (i === 0) contexto.moveTo(x, y)
      else contexto.lineTo(x, y)
    })
    contexto.stroke()
  }
}
