import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api.js'
import { BOTAO } from './Operacao.jsx'

export default function EtiquetaPedido({ filialId, pedido, onFechar, onEnfileirada }) {
  const dialogo = useRef(null)
  const [imagem, setImagem] = useState(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [conferida, setConferida] = useState(false)
  const incerto = pedido.etiqueta?.estado === 'INCERTO'
  const base = `/operacao/unidades/${filialId}/pedidos/${pedido.id}/etiqueta`
  useEffect(() => {
    const elemento = dialogo.current
    elemento.showModal()
    const controle = new AbortController()
    let url
    api.get(base, { responseType: 'blob', signal: controle.signal }).then(({ data }) => {
      if (controle.signal.aborted) return
      url = URL.createObjectURL(data); setImagem(url)
    }).catch(async (e) => {
      if (controle.signal.aborted) return
      let mensagem = 'Não foi possível carregar a etiqueta'
      try { mensagem = JSON.parse(await e.response.data.text()).detail || mensagem } catch { /* falha de conexão */ }
      setErro(mensagem)
    })
    return () => { controle.abort(); if (url) URL.revokeObjectURL(url); if (elemento.open) elemento.close() }
  }, [base])
  async function imprimir() {
    setOcupado(true); setErro('')
    try {
      const { data } = await api.post(base, { confirmar_risco_duplicidade: conferida })
      onEnfileirada(data.enfileirado ? `Etiqueta do pedido #${pedido.id} adicionada à fila.` : data.impressao?.erro || 'Não foi possível enviar a etiqueta.')
    } catch (e) { setErro(e.response?.data?.detail || 'Não foi possível enfileirar a etiqueta') }
    finally { setOcupado(false) }
  }
  return <dialog ref={dialogo} onCancel={(e) => { e.preventDefault(); if (!ocupado) onFechar() }} aria-labelledby="titulo-etiqueta"
    className="m-auto max-w-2xl space-y-4 rounded-2xl bg-panel p-5 text-slate-900 shadow-xl backdrop:bg-black/60 sm:p-6" style={{ width: 'calc(100vw - 2rem)' }}>
    <div><h2 id="titulo-etiqueta" className="text-xl font-bold">Etiqueta do pedido #{pedido.id}</h2><p className="mt-1 text-sm text-slate-700">89 mm × 36 mm · Refeição pronta</p></div>
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">{erro}</p>}
    {imagem ? <img src={imagem} alt={`Prévia da etiqueta do pedido ${pedido.id}`} className="w-full border border-slate-300 bg-white" /> : !erro && <p>Carregando prévia…</p>}
    <p className="text-sm text-slate-700">O envio usa a impressora de etiquetas cadastrada para esta unidade no painel de TI.</p>
    {incerto && <div className="space-y-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-950"><p>O envio anterior pode ter saído no papel. Confira a impressora antes de reenviar.</p>
      <label className="flex items-start gap-2"><input type="checkbox" checked={conferida} onChange={(e) => setConferida(e.target.checked)} />Conferi a impressão anterior e preciso de outra etiqueta.</label></div>}
    <div className="flex flex-wrap gap-3"><button disabled={ocupado} onClick={onFechar} className={`${BOTAO} bg-slate-100`}>Fechar</button>
      <button disabled={!imagem || ocupado || incerto && !conferida} onClick={imprimir} className={`${BOTAO} bg-brand text-white`}>{ocupado ? 'Enfileirando…' : pedido.etiqueta ? 'Reimprimir etiqueta' : 'Imprimir etiqueta'}</button></div>
  </dialog>
}
