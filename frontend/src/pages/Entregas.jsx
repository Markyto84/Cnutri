import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useOperacao } from '../hooks/useOperacao.js'
import { BOTAO, CabecalhoOperacao, ResumoPedido } from '../components/Operacao.jsx'
import { api } from '../services/api.js'
import { podeOperar, useAuth } from '../context/auth.js'
import FiltrosOperacao from '../components/FiltrosOperacao.jsx'
import AlertaDemora from '../components/AlertaDemora.jsx'
import { FILTROS_VAZIOS, filtrarPedidos } from '../services/painelOperacional.js'
import { Icone, Indicador } from '../components/Identidade.jsx'
import { etapaEntrega } from '../services/retiradaEntrega.js'
import { horarioBrasilia } from '../services/painelOperacional.js'

export default function Entregas() {
  const { filialId } = useParams()
  const { usuario } = useAuth()
  return <PaginaEntregas key={`${filialId}:${usuario?.id || 'publico'}`} filialId={filialId} />
}

function PaginaEntregas({ filialId }) {
  const painel = useOperacao(filialId, false, true)
  const { usuario, plantaoOnline, carregando: acessoCarregando } = useAuth()
  const { recarregar, aplicarPedido, setErro } = painel
  const autorizado = podeOperar(usuario, filialId, ['COPEIRA', 'NUTRICIONISTA', 'ADMIN_TI'])
  const copeiras = painel.copeiras
  const erroPlantao = painel.indisponivel ? 'Atualize seu acesso para consultar o plantão.' : ''
  const [selecionado, setSelecionado] = useState(null)
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState([])
  const emAndamento = useRef(new Set())
  const [filtros, setFiltros] = useState({ ...FILTROS_VAZIOS })
  const [etapa, setEtapa] = useState('TODAS')
  const prontos = painel.pedidos.filter((p) => p.status === 'PRONTO')
    .sort((a, b) => (a.concluido_em || a.criado_em).localeCompare(b.concluido_em || b.criado_em))
  const emEntrega = prontos.filter(p => etapaEntrega(p) === 'EM_ENTREGA')
  const filtrados = filtrarPedidos(prontos, filtros).filter(p => etapa === 'TODAS' || etapaEntrega(p) === etapa)
  const aguardandoPlantao = usuario?.perfil === 'COPEIRA' && !plantaoOnline

  const realizarEntrega = useCallback(async (pedido, copeiraId) => {
    if (!autorizado || pedido.recebimento_qr || pedido.retirada || emAndamento.current.has(pedido.id)) return
    emAndamento.current.add(pedido.id)
    setEnviando((ids) => [...ids, pedido.id])
    setAviso(''); setErro(null)
    try {
      const dados = usuario.perfil === 'COPEIRA' ? {} : { copeira_id: copeiraId }
      const { data } = await api.post(`/operacao/unidades/${filialId}/pedidos/${pedido.id}/entregar`, dados, { timeout: 15000 })
      setSelecionado(null)
      aplicarPedido({ id: data.pedido_id, status: 'ENTREGUE' })
      setAviso(`Atendimento do pedido #${data.pedido_id} finalizado. Entrega realizada por ${data.copeira_nome} em ${horarioBrasilia(data.entregue_em)}.`)
    } catch (e) {
      const detalhe = e.response?.data?.detail
      await recarregar()
      setErro(typeof detalhe === 'string' ? detalhe : 'Não foi possível registrar. Confira a atualização do painel antes de tentar novamente.')
    } finally {
      emAndamento.current.delete(pedido.id)
      setEnviando((ids) => ids.filter((id) => id !== pedido.id))
    }
  }, [autorizado, usuario, filialId, setErro, aplicarPedido, recarregar])

  const escolher = useCallback(async (pedido) => {
    if (!autorizado || pedido.recebimento_qr || pedido.retirada || pedido.em_entrega) return
    if (usuario.perfil === 'COPEIRA') { await realizarEntrega(pedido); return }
    setErro(null); setSelecionado(pedido)
    await recarregar()
  }, [usuario, autorizado, realizarEntrega, setErro, recarregar])

  return <main className="app-shell workspace-shell">
    <CabecalhoOperacao modo="entregas" painel={painel} filialId={filialId} />
    <p className="mb-4 rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Na entrega, a copeira escaneia o QR Code da filipeta no celular. O login será solicitado nesse dispositivo na primeira leitura; as próximas usarão a sessão ativa.</p>
    {painel.erro && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-900">{painel.erro}</p>}
    {aviso && <p role="status" className="mb-4 rounded-lg bg-emerald-50 p-4 text-emerald-950">{aviso}</p>}
    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Indicador titulo="Prontas para entrega" valor={prontos.length - emEntrega.length} icone="refeicao" />
      <Indicador titulo="Em entrega" valor={emEntrega.length} icone="entrega" />
      <Indicador titulo="Copeiras online" valor={copeiras.length} icone="pessoas" />
    </div>
    {erroPlantao && <p role="alert" className="mb-4 rounded-lg bg-amber-50 p-3 text-amber-950">{erroPlantao}</p>}
    {!painel.carregando && !painel.indisponivel && <section aria-label="Refeições prontas para entrega">
      <FiltrosOperacao pedidos={prontos} filtros={filtros} onChange={setFiltros} total={filtrados.length} />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-lg font-bold">Refeições prontas e em entrega</h2><p className="mt-1 text-sm text-slate-950">A identificação da copeira e o recebimento são registrados no celular pelo QR Code da filipeta.</p></div>
        <label className="text-sm font-semibold">Etapa da entrega<select className="mt-1 block min-h-11 rounded-lg border border-slate-300 bg-slate-50 px-3" value={etapa} onChange={e => setEtapa(e.target.value)}><option value="TODAS">Todas</option><option value="PRONTO">Prontas para entrega</option><option value="EM_ENTREGA">Em entrega</option></select></label></div>
      {!prontos.length && <div className="empty-state bg-panel"><Icone nome="entrega" tamanho={32} /><h3 className="font-bold">Nenhuma refeição aguardando entrega</h3><p className="text-sm text-slate-700">Os pedidos aparecem aqui quando a cozinha marca como Pronto.</p></div>}
      {prontos.length > 0 && !filtrados.length && <p className="rounded-xl bg-panel p-6">Nenhuma refeição corresponde aos filtros. Use “Limpar filtros” para ver todas.</p>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{filtrados.map((pedido) => <article key={pedido.id} className="order-card flex min-w-0 flex-col rounded-2xl border-t-4 border-brand-vibrant bg-panel p-4">
        <ResumoPedido pedido={pedido} />
        <AlertaDemora pedido={pedido} limites={painel.alertas} agora={painel.agora} />
        {pedido.concluido_em && <p className="mt-3 text-xs text-slate-700">Pronto às {new Date(pedido.concluido_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</p>}
        {etapaEntrega(pedido) === 'EM_ENTREGA' ? <div className="mt-4 space-y-2 rounded-xl bg-brand-soft p-4 text-sm text-brand-ink"><p className="font-bold">Em entrega</p>
          {pedido.retirada && <><p>Copeira: <strong>{pedido.retirada.copeira_nome}</strong></p><p className="text-xs">Identificação: {horarioBrasilia(pedido.retirada.retirada_em)}</p></>}
          <p>Aguardando confirmação do recebedor pelo QR Code da filipeta.</p></div>
          : pedido.recebimento_qr || !usuario ? <p className="mt-4 rounded-xl bg-brand-soft p-4 text-sm text-brand-ink">Escaneie o QR Code da filipeta no celular da copeira para identificar e concluir a entrega.</p>
            : autorizado && <div className="mt-auto space-y-2 pt-4">
            <button disabled={enviando.includes(pedido.id) || aguardandoPlantao || acessoCarregando} onClick={() => escolher(pedido)} className={`${BOTAO} w-full bg-brand-vibrant text-base text-brand-ink hover:bg-brand-vibrant-hover`}>
              {enviando.includes(pedido.id) ? 'Registrando…' : aguardandoPlantao ? 'Conectando ao plantão…' : 'Realizar entrega'}</button>
          </div>}
      </article>)}</div>
    </section>}
    {painel.carregando && <p className="rounded-xl bg-panel p-6">Carregando refeições…</p>}
    {selecionado && autorizado && <ModalEntrega pedido={selecionado} copeiras={copeiras} erro={painel.erro || erroPlantao} enviando={enviando.includes(selecionado.id)}
      pronto={prontos.some((p) => p.id === selecionado.id && !p.retirada)} onFechar={() => setSelecionado(null)}
      onConfirmar={(copeiraId) => realizarEntrega(selecionado, copeiraId)} />}
  </main>
}

function ModalEntrega({ pedido, copeiras, erro, enviando, pronto, onFechar, onConfirmar }) {
  const dialogo = useRef(null)
  const [copeiraId, setCopeiraId] = useState('')
  const disponivel = copeiras.some((c) => c.id === Number(copeiraId))

  useEffect(() => {
    const atual = dialogo.current
    atual.showModal()
    return () => { if (atual.open) atual.close() }
  }, [])

  function confirmar(evento) {
    evento.preventDefault()
    if (enviando || !disponivel || !pronto) return
    onConfirmar(Number(copeiraId))
  }

  return <dialog ref={dialogo} aria-labelledby="titulo-entrega" onCancel={(e) => { e.preventDefault(); if (!enviando) onFechar() }}
    className="m-auto max-h-[90dvh] overflow-y-auto rounded-2xl bg-panel p-5 text-slate-900 shadow-2xl backdrop:bg-black/60" style={{ width: 'min(28rem, calc(100vw - 2rem))' }}>
    <form onSubmit={confirmar} className="space-y-4">
      <div><h2 id="titulo-entrega" className="text-xl font-bold">Finalizar atendimento</h2><p className="mt-1 text-sm text-slate-700">Pedido #{pedido.id} · {pedido.nome_paciente || pedido.solicitante_nome}</p></div>
      {!pronto && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">Esta refeição já foi atualizada em outro painel e não está disponível para entrega.</p>}
      {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{erro}</p>}
      <label className="block text-sm font-semibold">Copeira do plantão
        <select required value={disponivel ? copeiraId : ''} onChange={(e) => setCopeiraId(e.target.value)} disabled={enviando || !copeiras.length || !pronto}
          className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal">
          <option value="">{copeiras.length ? 'Selecionar copeira' : 'Nenhuma copeira online'}</option>
          {copeiras.map((copeira) => <option key={copeira.id} value={copeira.id}>{copeira.nome}</option>)}
        </select>
      </label>
      <p className="text-sm text-slate-700">Selecione uma copeira online nesta unidade. Seu usuário também ficará registrado como responsável pela ação.</p>
      <p className="text-xs text-slate-700">Ao finalizar, a entrega e a data e hora serão registradas no relatório.</p>
      <div className="grid grid-cols-1 gap-2 pt-2 sm:grid-cols-2">
        <button type="button" disabled={enviando} onClick={onFechar} className={`${BOTAO} bg-slate-50`}>Voltar</button>
        <button type="submit" disabled={enviando || !disponivel || !pronto} className={`${BOTAO} bg-brand text-white hover:bg-brand-hover`}>{enviando ? 'Registrando…' : 'Finalizar atendimento'}</button>
      </div>
    </form>
  </dialog>
}
