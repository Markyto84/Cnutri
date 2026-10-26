import { useState } from 'react'
import { api } from '../services/api.js'
import { dataBrasilia, horarioBrasilia, mensagemErro } from '../services/painelOperacional.js'
import { CAMPO, PRIMARIO, SECUNDARIO, FiltroUnidade, Paginacao } from './ConsultaGestao.jsx'
import { useConsultaGestao } from '../hooks/useConsultaGestao.js'
import { ConfirmarReenvio } from './ImpressaoPedido.jsx'

const ESTADOS = { PENDENTE: 'Pendente', PROCESSANDO: 'Processando', ENVIADO: 'Enviado', FALHA: 'Falha', INCERTO: 'Envio incerto', CANCELADO: 'Cancelado' }

export default function CentralImpressoes({ filiais = [], filialId }) {
  const [filtros, setFiltros] = useState(() => ({ filial_id: '', estado: '', tipo: '', pedido_id: '',
    inicio: dataBrasilia(Date.now() - 6 * 86400000), fim: dataBrasilia() }))
  const [pagina, setPagina] = useState(1)
  const [ocupado, setOcupado] = useState(null)
  const [confirmar, setConfirmar] = useState(null)
  const [aviso, setAviso] = useState('')
  const [erroAcao, setErroAcao] = useState('')
  const params = Object.fromEntries(Object.entries({ ...filtros, filial_id: filialId || filtros.filial_id, pagina }).filter(([, v]) => v !== ''))
  const consulta = useConsultaGestao('/impressoes', params, 15000)
  function mudar(chave, valor) { setFiltros((f) => ({ ...f, [chave]: valor })); setPagina(1) }
  async function reenviar(item, confirmado = false) {
    if (ocupado) return
    if (item.estado === 'INCERTO' && !confirmado) { setConfirmar(item); return }
    setOcupado(item.id); setAviso(''); setErroAcao('')
    try {
      const { data } = await api.post(`/impressoes/${item.id}/reenviar`, { confirmar_risco_duplicidade: confirmado })
      setAviso(data.enfileirado ? `Novo envio do pedido #${item.pedido_id} registrado na fila (#${data.impressao.id}).`
        : data.impressao?.erro || 'Não foi possível preparar o envio.')
    } catch (e) { setErroAcao(mensagemErro(e)) } finally { setOcupado(null); consulta.atualizar() }
  }
  return <section className="min-w-0 space-y-4" aria-label="Central de impressões">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-bold">Central de impressões</h2>
      <p className="mt-1 text-sm text-slate-700">Filipetas e etiquetas das unidades permitidas. Atualização automática a cada 15 segundos.</p></div>
      <button className={SECUNDARIO} onClick={consulta.atualizar}>Atualizar central</button></div>
    <div className="grid min-w-0 gap-3 rounded-xl bg-panel p-4 sm:grid-cols-2 xl:grid-cols-3">
      {!filialId && <FiltroUnidade filiais={filiais} valor={filtros.filial_id} onChange={(v) => mudar('filial_id', v)} />}
      <label className="min-w-0 text-sm font-semibold">Situação<select className={CAMPO} value={filtros.estado} onChange={(e) => mudar('estado', e.target.value)}>
        <option value="">Todas</option>{Object.entries(ESTADOS).map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}</select></label>
      <label className="min-w-0 text-sm font-semibold">Documento<select className={CAMPO} value={filtros.tipo} onChange={(e) => mudar('tipo', e.target.value)}>
        <option value="">Todos</option><option value="FILIPETA">Filipeta</option><option value="ETIQUETA">Etiqueta</option></select></label>
      <label className="min-w-0 text-sm font-semibold">Número do pedido<input type="number" min={1} step={1} className={CAMPO} value={filtros.pedido_id} onChange={(e) => mudar('pedido_id', e.target.value)} /></label>
      <label className="min-w-0 text-sm font-semibold">Data inicial<input type="date" className={CAMPO} value={filtros.inicio} onChange={(e) => mudar('inicio', e.target.value)} /></label>
      <label className="min-w-0 text-sm font-semibold">Data final<input type="date" className={CAMPO} value={filtros.fim} onChange={(e) => mudar('fim', e.target.value)} /></label>
    </div>
    <p className="text-sm text-slate-700">“Enviado” confirma a transmissão dos dados. Confira o papel para confirmar a impressão física. Reenvios ficam disponíveis para o último trabalho com falha ou envio incerto de pedidos em operação.</p>
    {(consulta.erro || erroAcao) && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{erroAcao || consulta.erro}</p>}
    {aviso && <p role="status" className="rounded-lg bg-brand-soft p-3 text-brand-ink">{aviso}</p>}
    {consulta.carregando && <p>Carregando impressões…</p>}
    {consulta.dados && <>
      <Paginacao {...consulta.dados} onChange={setPagina} />
      {!consulta.dados.itens.length && <p className="rounded-xl bg-panel p-6">Nenhuma impressão encontrada com estes filtros.</p>}
      <div className="space-y-3">{consulta.dados.itens.map((item) => <article key={item.id} className="min-w-0 space-y-3 rounded-xl bg-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-bold">Pedido #{item.pedido_id} · {item.tipo_documento === 'ETIQUETA' ? 'Etiqueta' : 'Filipeta'}</h3>
          <p className="mt-1 break-words text-sm text-slate-700">{item.unidade} · Trabalho #{item.id}</p></div>
          <strong className={`rounded px-3 py-1 text-sm ${['FALHA', 'INCERTO'].includes(item.estado) ? 'bg-amber-100 text-amber-950' : 'bg-white text-slate-800'}`}>{ESTADOS[item.estado] || item.estado}</strong></div>
        <div className="grid gap-2 text-sm text-slate-700 sm:grid-cols-2 xl:grid-cols-3"><p>Criado: {horarioBrasilia(item.criado_em)}</p><p>Tentativas: {item.tentativas}</p>
          {item.enviado_em && <p>Enviado: {horarioBrasilia(item.enviado_em)}</p>}
          {item.estado === 'PENDENTE' && item.tentativas > 0 && <p>Nova tentativa: {horarioBrasilia(item.proxima_tentativa_em)}</p>}</div>
        {item.erro && <p className="break-words rounded-lg bg-white p-3 text-sm text-amber-950">{item.erro}</p>}
        {item.pode_reenviar && <button disabled={Boolean(ocupado)} className={PRIMARIO} onClick={() => reenviar(item)}>{ocupado === item.id ? 'Enfileirando…' : item.estado === 'INCERTO' ? 'Conferir e reenviar' : 'Reenviar'}</button>}
      </article>)}</div>
    </>}
    {confirmar && <ConfirmarReenvio pedido={{ id: confirmar.pedido_id }} etiqueta={confirmar.tipo_documento === 'ETIQUETA'} onCancelar={() => setConfirmar(null)}
      onConfirmar={() => { const item = confirmar; setConfirmar(null); reenviar(item, true) }} />}
  </section>
}
