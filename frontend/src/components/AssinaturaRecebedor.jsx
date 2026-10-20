import { useEffect, useRef } from 'react'

function desenhar(canvas, tracos) {
  const contexto = canvas.getContext('2d')
  contexto.fillStyle = '#ffffff'
  contexto.fillRect(0, 0, canvas.width, canvas.height)
  contexto.strokeStyle = '#141414'
  contexto.lineWidth = 6
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

export default function AssinaturaRecebedor({ tracos, onChange, disabled }) {
  const canvas = useRef(null)
  const desenhoAtual = useRef(null)
  const limite = tracos.length >= 40 || tracos.reduce((n, t) => n + t.length, 0) >= 6500

  useEffect(() => { desenhar(canvas.current, tracos) }, [tracos])

  function ponto(evento) {
    const area = canvas.current.getBoundingClientRect()
    const normalizar = (n) => Math.round(Math.min(1, Math.max(0, n)) * 10000) / 10000
    return { x: normalizar((evento.clientX - area.left) / area.width), y: normalizar((evento.clientY - area.top) / area.height) }
  }

  function iniciar(evento) {
    if (disabled || limite || desenhoAtual.current || evento.button !== 0) return
    evento.preventDefault()
    evento.currentTarget.setPointerCapture(evento.pointerId)
    desenhoAtual.current = { id: evento.pointerId, pontos: [ponto(evento)] }
  }

  function mover(evento) {
    const atual = desenhoAtual.current
    if (!atual || atual.id !== evento.pointerId) return
    if (atual.pontos.length >= 1500) return
    atual.pontos.push(ponto(evento))
    desenhar(canvas.current, [...tracos, atual.pontos])
  }

  function terminar(evento) {
    const atual = desenhoAtual.current
    if (!atual || atual.id !== evento.pointerId) return
    desenhoAtual.current = null
    if (atual.pontos.length > 1) onChange([...tracos, atual.pontos])
    else desenhar(canvas.current, tracos)
    if (evento.currentTarget.hasPointerCapture(evento.pointerId)) evento.currentTarget.releasePointerCapture(evento.pointerId)
  }

  return <div className="space-y-2">
    <p id="instrucao-assinatura" className="text-sm text-slate-700">Assine no quadro branco com o dedo, a caneta ou o mouse.</p>
    <canvas ref={canvas} width={1000} height={500} role="img" aria-label="Área de assinatura do recebedor" aria-describedby="instrucao-assinatura"
      onPointerDown={iniciar} onPointerMove={mover} onPointerUp={terminar} onPointerCancel={terminar}
      className={`aspect-[2/1] w-full rounded-lg border-2 border-slate-400 bg-white ${disabled ? 'opacity-60' : 'cursor-crosshair'}`}
      style={{ touchAction: 'none' }}>Área de assinatura: use um navegador com suporte a desenho.</canvas>
    <div className="flex items-center justify-between gap-3">
      <span role="status" className="text-xs text-slate-700">{tracos.length ? 'Assinatura preenchida' : 'Assinatura obrigatória'}</span>
      <button type="button" disabled={disabled || !tracos.length} onClick={() => onChange([])} className="min-h-11 rounded-lg bg-slate-50 px-3 text-sm font-semibold disabled:opacity-50">Limpar assinatura</button>
    </div>
    {limite && <p role="alert" className="text-sm text-amber-900">Limite de traços atingido. Se precisar refazer, limpe a assinatura.</p>}
  </div>
}
