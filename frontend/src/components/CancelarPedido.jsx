import { useEffect, useRef, useState } from 'react'
import { BOTAO } from './Operacao.jsx'

export default function CancelarPedido({ pedido, disponivel, onFechar, onConfirmar }) {
  const ref = useRef(null)
  const bloqueado = useRef(false)
  const [motivo, setMotivo] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  useEffect(() => {
    const dialogo = ref.current
    dialogo.showModal()
    return () => { if (dialogo.open) dialogo.close() }
  }, [])

  async function confirmar(evento) {
    evento.preventDefault()
    if (bloqueado.current || !disponivel || motivo.trim().length < 5) return
    bloqueado.current = true
    setEnviando(true); setErro('')
    try {
      await onConfirmar(motivo.trim())
      onFechar()
    } catch (e) {
      const detalhe = e.response?.data?.detail
      setErro(typeof detalhe === 'string' ? detalhe : 'Não foi possível cancelar o pedido. Confira a situação e tente novamente.')
    } finally { bloqueado.current = false; setEnviando(false) }
  }

  return <dialog ref={ref} onCancel={(e) => { e.preventDefault(); if (!enviando) onFechar() }} aria-labelledby="titulo-cancelamento"
    className="m-auto max-h-[90dvh] max-w-lg overflow-y-auto rounded-2xl bg-panel p-5 text-slate-900 shadow-xl backdrop:bg-black/60 sm:p-6"
    style={{ width: 'calc(100vw - 2rem)' }}>
    <form onSubmit={confirmar} className="space-y-4">
      <h2 id="titulo-cancelamento" className="text-xl font-bold">Cancelar pedido #{pedido.id}</h2>
      <p className="break-words text-sm">{pedido.nome_paciente || pedido.solicitante_nome || `Solicitação #${pedido.id}`}</p>
      <label className="block text-sm font-semibold">Motivo do cancelamento *
        <textarea autoFocus required minLength={5} maxLength={1000} rows={4} value={motivo} disabled={enviando}
          onChange={(e) => setMotivo(e.target.value)} aria-describedby="orientacao-cancelamento"
          className="mt-2 w-full rounded-lg border border-slate-300 bg-white p-3 text-base font-normal" />
      </label>
      <p id="orientacao-cancelamento" className="text-xs text-slate-700">Informe de 5 a 1.000 caracteres. O motivo e o horário ficarão registrados no relatório com a identificação “Painel da cozinha (sem login)”.</p>
      {!disponivel && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Este pedido não está mais disponível para cancelamento. Volte ao painel para conferir a situação atual.</p>}
      {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">{erro}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={enviando} onClick={onFechar} className={`${BOTAO} bg-slate-100`}>Voltar</button>
        <button disabled={enviando || !disponivel || motivo.trim().length < 5} className={`${BOTAO} flex-1 bg-red-700 text-white hover:bg-red-800`}>{enviando ? 'Cancelando…' : 'Confirmar cancelamento'}</button>
      </div>
    </form>
  </dialog>
}
