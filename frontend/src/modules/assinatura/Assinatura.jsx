import { useEffect, useId, useRef } from 'react'
import { desenharAssinatura } from './desenho.js'
import { capacidadeNovoTraco, CONTRATO_ASSINATURA, normalizarPonto, validarAssinatura } from './modelo.js'

export default function Assinatura({ tracos, onChange, disabled = false,
  rotulo = 'Área de assinatura', instrucao = 'Assine no quadro branco com o dedo, a caneta ou o mouse.' }) {
  const canvas = useRef(null)
  const desenhoAtual = useRef(null)
  const instrucaoId = useId()
  const capacidade = capacidadeNovoTraco(tracos)
  const erro = validarAssinatura(tracos)

  useEffect(() => {
    if (disabled) desenhoAtual.current = null
    desenharAssinatura(canvas.current, tracos)
  }, [tracos, disabled])

  function ponto(evento) {
    return normalizarPonto(evento.clientX, evento.clientY, canvas.current.getBoundingClientRect())
  }

  function iniciar(evento) {
    if (disabled || !capacidade || desenhoAtual.current || evento.button !== 0) return
    const primeiro = ponto(evento)
    if (!primeiro) return
    evento.preventDefault()
    evento.currentTarget.setPointerCapture(evento.pointerId)
    desenhoAtual.current = { id: evento.pointerId, pontos: [primeiro], capacidade }
  }

  function mover(evento) {
    const atual = desenhoAtual.current
    if (disabled || !atual || atual.id !== evento.pointerId || atual.pontos.length >= atual.capacidade) return
    const proximo = ponto(evento)
    if (!proximo) return
    atual.pontos.push(proximo)
    desenharAssinatura(canvas.current, [...tracos, atual.pontos])
  }

  function terminar(evento, cancelar = false) {
    const atual = desenhoAtual.current
    if (!atual || atual.id !== evento.pointerId) return
    desenhoAtual.current = null
    if (!disabled && !cancelar && atual.pontos.length >= CONTRATO_ASSINATURA.minPontosTraco) onChange([...tracos, atual.pontos])
    else desenharAssinatura(canvas.current, tracos)
    if (evento.currentTarget.hasPointerCapture(evento.pointerId)) evento.currentTarget.releasePointerCapture(evento.pointerId)
  }

  function limpar() {
    desenhoAtual.current = null
    onChange([])
  }

  return <div className="space-y-2">
    <p id={instrucaoId} className="text-sm text-slate-700">{instrucao}</p>
    <canvas ref={canvas} width={CONTRATO_ASSINATURA.largura} height={CONTRATO_ASSINATURA.altura} role="img"
      aria-label={rotulo} aria-describedby={instrucaoId} aria-disabled={disabled}
      onPointerDown={iniciar} onPointerMove={mover} onPointerUp={terminar}
      onPointerCancel={(evento) => terminar(evento, true)} onLostPointerCapture={(evento) => terminar(evento, true)}
      className={`aspect-[2/1] w-full rounded-lg border-2 border-slate-400 bg-white ${disabled ? 'opacity-60' : 'cursor-crosshair'}`}
      style={{ touchAction: 'none' }}>Área de assinatura: use um navegador com suporte a desenho.</canvas>
    <div className="flex items-center justify-between gap-3">
      <span role="status" className="text-xs text-slate-700">{tracos.length ? erro ? 'Assinatura incompleta' : 'Assinatura preenchida' : 'Assinatura obrigatória'}</span>
      <button type="button" disabled={disabled || !tracos.length} onClick={limpar} className="min-h-11 rounded-lg bg-slate-50 px-3 text-sm font-semibold disabled:opacity-50">Limpar assinatura</button>
    </div>
    {!capacidade && <p role="alert" className="text-sm text-amber-900">Limite de traços atingido. Se precisar refazer, limpe a assinatura.</p>}
    {tracos.length > 0 && erro && capacidade > 0 && <p role="alert" className="text-sm text-amber-900">{erro}</p>}
  </div>
}
