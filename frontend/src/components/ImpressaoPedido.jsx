import { useEffect, useRef } from 'react'
import { textoImpressao } from '../services/solicitacoes.js'
import { BOTAO } from './Operacao.jsx'

export function EstadoImpressao({ impressao, etiqueta = false }) {
  if (!impressao) return null
  const falha = ['FALHA', 'INCERTO'].includes(impressao.estado)
  return <div className={`mt-3 rounded-lg p-3 text-xs ${falha ? 'bg-red-50 text-red-900' : 'bg-slate-100 text-slate-700'}`}>
    <p className="font-semibold">{etiqueta ? textoImpressao(impressao.estado).replace(/Filipeta/g, 'Etiqueta').replace(/filipeta/g, 'etiqueta').replace(/^Impressão/, 'Impressão da etiqueta').replace(/^Envio/, 'Envio da etiqueta') : textoImpressao(impressao.estado)}</p>
    {impressao.erro && <p className="mt-1">{impressao.erro}{impressao.estado === 'PENDENTE' ? '. Nova tentativa agendada.' : ''}</p>}
  </div>
}

export function ConfirmarReenvio({ pedido, onCancelar, onConfirmar }) {
  const ref = useRef(null)
  useEffect(() => {
    const dialogo = ref.current
    dialogo.showModal()
    return () => { if (dialogo.open) dialogo.close() }
  }, [])
  return <dialog ref={ref} onCancel={(e) => { e.preventDefault(); onCancelar() }} aria-labelledby="confirmar-reenvio"
    className="m-auto max-w-lg space-y-4 rounded-2xl bg-panel p-6 text-slate-900 shadow-xl backdrop:bg-black/60"
    style={{ width: 'calc(100vw - 2rem)' }}>
    <h2 id="confirmar-reenvio" className="text-xl font-bold">Conferir filipeta do pedido #{pedido.id}</h2>
    <p className="text-sm">O envio anterior foi interrompido e pode ter saído total ou parcialmente. Confira a impressora antes de solicitar outra cópia.</p>
    <div className="flex flex-wrap gap-3"><button onClick={onCancelar} className={`${BOTAO} bg-slate-100`}>Voltar e conferir</button>
      <button onClick={onConfirmar} className={`${BOTAO} bg-brand text-white`}>Conferi o papel, reenviar</button></div>
  </dialog>
}
