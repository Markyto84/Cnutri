import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useOperacao } from '../hooks/useOperacao.js'
import { BOTAO, CabecalhoOperacao, ResumoPedido } from '../components/Operacao.jsx'
import { api } from '../services/api.js'
import { podeOperar, useAuth } from '../context/auth.js'
import AssinaturaRecebedor from '../components/AssinaturaRecebedor.jsx'
import FiltrosOperacao from '../components/FiltrosOperacao.jsx'
import AlertaDemora from '../components/AlertaDemora.jsx'
import { FILTROS_VAZIOS, filtrarPedidos } from '../services/painelOperacional.js'

export default function Entregas() {
  const { filialId } = useParams()
  const { usuario } = useAuth()
  return <PaginaEntregas key={`${filialId}:${usuario?.id || 'publico'}`} filialId={filialId} />
}

function PaginaEntregas({ filialId }) {
  const painel = useOperacao(filialId, false, true)
  const { usuario } = useAuth()
  const autorizado = podeOperar(usuario, filialId, ['COPEIRA', 'NUTRICIONISTA', 'ADMIN_TI'])
  const copeiras = painel.copeiras
  const erroPlantao = painel.indisponivel ? 'Atualize seu acesso para consultar o plantão.' : ''
  const [selecionado, setSelecionado] = useState(null)
  const [aviso, setAviso] = useState('')
  const [filtros, setFiltros] = useState({ ...FILTROS_VAZIOS })
  const prontos = painel.pedidos.filter((p) => p.status === 'PRONTO')
    .sort((a, b) => (a.concluido_em || a.criado_em).localeCompare(b.concluido_em || b.criado_em))
  const filtrados = filtrarPedidos(prontos, filtros)

  async function escolher(pedido) {
    if (!autorizado) return
    setSelecionado(pedido)
    await painel.recarregar()
  }

  function concluida(entrega) {
    setSelecionado(null)
    painel.aplicarPedido({ id: entrega.pedido_id, status: 'ENTREGUE' })
    const horario = new Date(entrega.entregue_em).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
    setAviso(`Pedido #${entrega.pedido_id} entregue por ${entrega.copeira_nome} e recebido por ${entrega.recebedor_nome} em ${horario}. Assinatura registrada.`)
  }

  return <main className="min-h-screen bg-app-background p-3 text-slate-900 sm:p-5">
    <CabecalhoOperacao modo="entregas" painel={painel} filialId={filialId} />
    {!autorizado && <p className="mb-4 rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Entre com uma conta de copeira ou gestão autorizada nesta unidade para registrar entregas e assinaturas.</p>}
    {painel.erro && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-900">{painel.erro}</p>}
    {aviso && <p role="status" className="mb-4 rounded-lg bg-emerald-50 p-4 text-emerald-950">{aviso}</p>}
    <div className="mb-4 grid grid-cols-2 gap-3">
      <div className="rounded-xl bg-panel p-4"><p className="text-sm text-slate-700">Refeições prontas</p><strong className="text-3xl">{prontos.length}</strong></div>
      <div className="rounded-xl bg-panel p-4"><p className="text-sm text-slate-700">Copeiras online</p><strong className="text-3xl">{copeiras.length}</strong></div>
    </div>
    {erroPlantao && <p role="alert" className="mb-4 rounded-lg bg-amber-50 p-3 text-amber-950">{erroPlantao}</p>}
    {!painel.carregando && !painel.indisponivel && <section aria-label="Refeições prontas para entrega">
      <FiltrosOperacao pedidos={prontos} filtros={filtros} onChange={setFiltros} total={filtrados.length} />
      <div className="mb-4"><h2 className="text-lg font-bold">Prontas para entrega</h2><p className="mt-1 text-sm text-slate-950">{usuario?.perfil === 'COPEIRA' ? 'Registre suas entregas e colete a assinatura do recebedor.' : 'Selecione a refeição e indique a copeira que fará a entrega.'}</p></div>
      {!prontos.length && <div className="rounded-2xl bg-panel p-8 text-center"><h3 className="font-bold">Nenhuma refeição aguardando entrega</h3><p className="mt-2 text-sm text-slate-700">Os pedidos aparecem aqui quando a cozinha marca como Pronto.</p></div>}
      {prontos.length > 0 && !filtrados.length && <p className="rounded-xl bg-panel p-6">Nenhuma refeição corresponde aos filtros. Use “Limpar filtros” para ver todas.</p>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{filtrados.map((pedido) => <article key={pedido.id} className="flex min-w-0 flex-col rounded-2xl border-t-4 border-brand-vibrant bg-panel p-4 shadow-sm">
        <ResumoPedido pedido={pedido} />
        <AlertaDemora pedido={pedido} limites={painel.alertas} agora={painel.agora} />
        {pedido.concluido_em && <p className="mt-3 text-xs text-slate-700">Pronto às {new Date(pedido.concluido_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</p>}
        {autorizado && <div className="mt-auto pt-4"><button onClick={() => escolher(pedido)} className={`${BOTAO} w-full bg-brand-vibrant text-base text-brand-ink hover:bg-brand-vibrant-hover`}>Entregar</button></div>}
      </article>)}</div>
    </section>}
    {painel.carregando && <p className="rounded-xl bg-panel p-6">Carregando refeições…</p>}
    {selecionado && autorizado && <ModalEntrega pedido={selecionado} filialId={filialId} copeiras={usuario.perfil === 'COPEIRA' ? copeiras.filter((c) => c.id === usuario.id) : copeiras} copeiraPropria={usuario.perfil === 'COPEIRA' ? usuario.id : null} erroPlantao={erroPlantao}
      pronto={prontos.some((p) => p.id === selecionado.id)} onFechar={() => setSelecionado(null)} onConcluir={concluida}
      onRecarregar={() => painel.recarregar()} />}
  </main>
}

function ModalEntrega({ pedido, filialId, copeiras, copeiraPropria, erroPlantao, pronto, onFechar, onConcluir, onRecarregar }) {
  const dialogo = useRef(null)
  const [copeiraId, setCopeiraId] = useState(copeiraPropria ? String(copeiraPropria) : '')
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const [etapa, setEtapa] = useState(1)
  const [recebedor, setRecebedor] = useState('')
  const [tracos, setTracos] = useState([])
  const disponivel = copeiras.some((c) => c.id === Number(copeiraId))

  useEffect(() => {
    const atual = dialogo.current
    atual.showModal()
    return () => { if (atual.open) atual.close() }
  }, [])

  async function confirmar(evento) {
    evento.preventDefault()
    if (enviando || !disponivel || !pronto) return
    if (etapa === 1) { setEtapa(2); setErro(''); return }
    if (recebedor.trim().length < 3 || !tracos.length) return
    setEnviando(true)
    setErro('')
    try {
      const { data } = await api.post(`/operacao/unidades/${filialId}/pedidos/${pedido.id}/entregar`, {
        copeira_id: Number(copeiraId), recebedor_nome: recebedor.trim(), assinatura: { tracos },
      })
      onConcluir(data)
    } catch (e) {
      const detalhe = e.response?.data?.detail
      setErro(Array.isArray(detalhe) ? detalhe.map((item) => item.msg.replace(/^Value error, /, '')).join('. ')
        : detalhe || 'Não foi possível confirmar a entrega. Atualize a lista antes de tentar novamente')
      onRecarregar()
    } finally { setEnviando(false) }
  }

  return <dialog ref={dialogo} aria-labelledby="titulo-entrega" onCancel={(e) => { e.preventDefault(); if (!enviando) onFechar() }}
    className="m-auto max-h-[90dvh] overflow-y-auto rounded-2xl bg-panel p-5 text-slate-900 shadow-2xl backdrop:bg-black/60" style={{ width: 'min(28rem, calc(100vw - 2rem))' }}>
    <form onSubmit={confirmar} className="space-y-4">
      <div><p className="mb-1 text-xs font-semibold text-slate-700">Etapa {etapa} de 2</p><h2 id="titulo-entrega" className="text-xl font-bold">{etapa === 1 ? 'Entregar refeição' : 'Assinatura do recebedor'}</h2><p className="mt-1 text-sm text-slate-700">Pedido #{pedido.id} · {pedido.nome_paciente || pedido.solicitante_nome}</p></div>
      {!pronto && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">Esta refeição já foi atualizada em outro painel e não está disponível para entrega.</p>}
      {(erro || erroPlantao) && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{erro || erroPlantao}</p>}
      {etapa === 1 ? <><label className="block text-sm font-semibold">Copeira do plantão
        <select required value={disponivel ? copeiraId : ''} onChange={(e) => setCopeiraId(e.target.value)} disabled={enviando || !copeiras.length || !pronto}
          className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal">
          <option value="">{copeiras.length ? 'Selecionar copeira' : 'Nenhuma copeira online'}</option>
          {copeiras.map((copeira) => <option key={copeira.id} value={copeira.id}>{copeira.nome}</option>)}
        </select>
      </label>
      <p className="text-sm text-slate-700">{copeiraPropria ? 'A entrega ficará registrada no seu nome.' : 'Selecione uma copeira online nesta unidade. Seu usuário também ficará registrado como responsável pela ação.'}</p>
      {!copeiras.length && <Link to={`/login?unidade=${filialId}`} className="block font-semibold text-brand underline">Entrar no plantão com uma conta de copeira</Link>}
      </> : <>
        <p className="text-sm text-slate-700"><strong>Copeira:</strong> {copeiras.find((c) => c.id === Number(copeiraId))?.nome || 'Indisponível no plantão'}</p>
        {!disponivel && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">A copeira saiu do plantão. Volte e selecione uma copeira online.</p>}
        <label className="block text-sm font-semibold">Nome do recebedor
          <input required minLength={3} maxLength={120} autoComplete="off" value={recebedor} onChange={(e) => setRecebedor(e.target.value)} disabled={enviando}
            className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 text-base font-normal" />
        </label>
        <AssinaturaRecebedor tracos={tracos} onChange={setTracos} disabled={enviando || !pronto} />
        <p className="text-xs text-slate-700">Ao finalizar, a assinatura e a data e hora da entrega serão salvas no relatório.</p>
      </>}
      <div className="grid grid-cols-1 gap-2 pt-2 sm:grid-cols-2">
        <button type="button" disabled={enviando} onClick={() => etapa === 1 ? onFechar() : setEtapa(1)} className={`${BOTAO} bg-slate-50`}>Voltar</button>
        <button type="submit" disabled={enviando || !disponivel || !pronto || Boolean(erroPlantao) || (etapa === 2 && (!tracos.length || recebedor.trim().length < 3))} className={`${BOTAO} bg-brand text-white hover:bg-brand-hover`}>{enviando ? 'Registrando…' : etapa === 1 ? 'Continuar para assinatura' : 'Finalizar entrega'}</button>
      </div>
    </form>
  </dialog>
}
