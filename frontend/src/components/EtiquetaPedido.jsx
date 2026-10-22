import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api.js'
import { BOTAO } from './Operacao.jsx'

export default function EtiquetaPedido({ filialId, pedido, onFechar, onEnfileirada }) {
  const dialogo = useRef(null)
  const [imagens, setImagens] = useState([])
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [conferida, setConferida] = useState(false)
  const incerto = pedido.etiqueta?.estado === 'INCERTO'
  const base = `/operacao/unidades/${filialId}/pedidos/${pedido.id}/etiqueta`
  useEffect(() => {
    const elemento = dialogo.current
    elemento.showModal()
    const controle = new AbortController()
    const urls = []
    async function carregar() {
      const lote = []
      let quantidade = 1
      for (let indice = 0; indice < quantidade; indice++) {
        const { data, headers } = await api.get(base, { responseType: 'blob', signal: controle.signal, params: { indice } })
        if (controle.signal.aborted) return
        if (indice === 0) quantidade = headers['x-quantidade-etiquetas'] === '2' ? 2 : 1
        const url = URL.createObjectURL(data)
        urls.push(url)
        lote.push({ url, destinatario: headers['x-destinatario-etiqueta'] || 'Paciente' })
      }
      if (!controle.signal.aborted) setImagens(lote)
    }
    carregar().catch(async (e) => {
      if (controle.signal.aborted) return
      let mensagem = 'Não foi possível carregar a etiqueta'
      try { mensagem = JSON.parse(await e.response.data.text()).detail || mensagem } catch { /* falha de conexão */ }
      setErro(mensagem)
    })
    return () => { controle.abort(); urls.forEach((url) => URL.revokeObjectURL(url)); if (elemento.open) elemento.close() }
  }, [base])
  async function imprimir() {
    setOcupado(true); setErro('')
    try {
      const { data } = await api.post(base, { confirmar_risco_duplicidade: conferida })
      onEnfileirada(data.enfileirado ? `${imagens.length === 2 ? 'Duas etiquetas do pedido' : 'Etiqueta do pedido'} #${pedido.id} ${imagens.length === 2 ? 'adicionadas' : 'adicionada'} à fila.` : data.impressao?.erro || 'Não foi possível enviar a etiqueta.')
    } catch (e) { setErro(e.response?.data?.detail || 'Não foi possível enfileirar a etiqueta') }
    finally { setOcupado(false) }
  }
  return <dialog ref={dialogo} onCancel={(e) => { e.preventDefault(); if (!ocupado) onFechar() }} aria-labelledby="titulo-etiqueta"
    className="m-auto max-h-[calc(100dvh-2rem)] max-w-2xl space-y-4 overflow-y-auto rounded-2xl bg-panel p-5 text-slate-900 shadow-xl backdrop:bg-black/60 sm:p-6" style={{ width: 'calc(100vw - 2rem)' }}>
    <div><h2 id="titulo-etiqueta" className="text-xl font-bold">{imagens.length === 2 ? 'Etiquetas' : 'Etiqueta'} do pedido #{pedido.id}</h2><p className="mt-1 text-sm text-slate-700">89 mm × 36 mm por etiqueta · Refeição pronta{imagens.length === 2 && ' · 2 etiquetas: paciente e acompanhante'}</p></div>
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">{erro}</p>}
    {imagens.length ? <div className="max-h-[52dvh] space-y-4 overflow-y-auto">{imagens.map(({ url, destinatario }) => <figure key={destinatario}>
      <figcaption className="mb-1 text-sm font-semibold">{destinatario}</figcaption>
      <img src={url} alt={`Prévia da etiqueta: ${destinatario}, pedido ${pedido.id}`} className="w-full border border-slate-300 bg-white" />
    </figure>)}</div> : !erro && <p>Carregando prévia…</p>}
    <p className="text-sm text-slate-700">O envio usa a impressora de etiquetas cadastrada para esta unidade no painel de TI.</p>
    {incerto && <div className="space-y-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-950"><p>O envio anterior pode ter saído no papel, inclusive parcialmente. Confira a impressora antes de reenviar.{imagens.length === 2 && ' A reimpressão envia novamente as duas etiquetas.'}</p>
      <label className="flex items-start gap-2"><input type="checkbox" checked={conferida} onChange={(e) => setConferida(e.target.checked)} />Conferi a impressão anterior e preciso imprimir novamente.</label></div>}
    <div className="flex flex-wrap gap-3"><button disabled={ocupado} onClick={onFechar} className={`${BOTAO} bg-slate-100`}>Fechar</button>
      <button disabled={!imagens.length || ocupado || incerto && !conferida} onClick={imprimir} className={`${BOTAO} bg-brand text-white`}>{ocupado ? 'Enfileirando…' : `${pedido.etiqueta ? 'Reimprimir' : 'Imprimir'} ${imagens.length === 2 ? '2 etiquetas' : 'etiqueta'}`}</button></div>
  </dialog>
}
