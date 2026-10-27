import { useState } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { useOperacao } from '../hooks/useOperacao.js'
import { cozinhaApi } from '../services/cozinhaApi.js'
import { BOTAO, CabecalhoOperacao, ResumoPedido } from '../components/Operacao.jsx'
import { ConfirmarReenvio, EstadoImpressao } from '../components/ImpressaoPedido.jsx'
import EtiquetaPedido from '../components/EtiquetaPedido.jsx'
import FiltrosOperacao from '../components/FiltrosOperacao.jsx'
import AlertaDemora from '../components/AlertaDemora.jsx'
import CancelarPedido from '../components/CancelarPedido.jsx'
import { FILTROS_VAZIOS, filtrarPedidos } from '../services/painelOperacional.js'
import { caminhoCozinha } from '../services/rotasUnidades.js'

const COLUNAS = [
  { status: 'PENDENTE', titulo: 'Pendentes', cor: 'border-t-amber-500' },
  { status: 'EM_PREPARO', titulo: 'Em preparo', cor: 'border-t-brand' },
  { status: 'PRONTO', titulo: 'Prontos', cor: 'border-t-emerald-600' },
]

export default function Cozinha() {
  const { unidade } = useParams()
  return <Dashboard key={unidade} unidade={unidade} />
}

function Dashboard({ unidade }) {
  const painel = useOperacao(unidade, true, false, true)
  const filialId = painel.filial?.id
  const localizacao = useLocation()
  const [filtro, setFiltro] = useState('PENDENTE')
  const [ocupados, setOcupados] = useState([])
  const [aviso, setAviso] = useState('')
  const [confirmar, setConfirmar] = useState(null)
  const [etiquetar, setEtiquetar] = useState(null)
  const [cancelar, setCancelar] = useState(null)
  const [filtros, setFiltros] = useState({ ...FILTROS_VAZIOS })
  const filtrados = filtrarPedidos(painel.pedidos, filtros)
  const falhas = filtrados.filter((p) => ['FALHA', 'INCERTO'].includes(p.impressao?.estado)).length

  async function agir(pedido, status, riscoConfirmado = false) {
    if (painel.indisponivel || ocupados.includes(pedido.id)) return
    if (!status && pedido.impressao?.estado === 'INCERTO' && !riscoConfirmado) { setConfirmar(pedido); return }
    setOcupados((atuais) => [...atuais, pedido.id])
    setAviso('')
    try {
      const base = `/unidades/${filialId}/pedidos/${pedido.id}`
      if (status) {
        const { data } = await cozinhaApi.patch(base + '/status', { status })
        painel.aplicarPedido(data)
      } else {
        const { data } = await cozinhaApi.post(base + '/reimprimir', { confirmar_risco_duplicidade: riscoConfirmado })
        setAviso(data.enfileirado ? `Filipeta do pedido #${pedido.id} adicionada à fila.` : data.impressao?.erro || 'Não foi possível preparar a impressão.')
        await painel.recarregar()
      }
    } catch (e) {
      painel.setErro(e.response?.data?.detail || 'Não foi possível atualizar o pedido')
    } finally { setOcupados((atuais) => atuais.filter((id) => id !== pedido.id)) }
  }

  async function cancelarPedido(motivo) {
    if (painel.indisponivel || !cancelar) throw new Error('Cancelamento indisponível')
    const { data } = await cozinhaApi.patch(`/unidades/${filialId}/pedidos/${cancelar.id}/status`, { status: 'CANCELADO', motivo })
    painel.aplicarPedido(data)
    setAviso(`Pedido #${cancelar.id} cancelado. Motivo registrado no relatório.`)
  }

  if (painel.filial && unidade !== painel.filial.codigo_slug) {
    return <Navigate replace to={{ pathname: caminhoCozinha(painel.filial), search: localizacao.search, hash: localizacao.hash }} />
  }

  return <main className="min-h-screen bg-app-background p-3 text-slate-900 sm:p-5">
    <CabecalhoOperacao modo="cozinha" painel={painel} filialId={filialId} />
    <p className="mb-4 rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Preparo, cancelamento e impressão disponíveis sem login. As etapas são registradas como “Painel da cozinha (sem login)”. A entrega é finalizada pela copeira no painel de entregas.</p>
    {painel.erro && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-900">{painel.erro}</p>}
    {aviso && <p role="status" className="mb-4 rounded-lg bg-brand-soft p-3 text-brand-ink">{aviso}</p>}
    {falhas > 0 && <p role="alert" className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{falhas} pedido(s) com falha ou envio de filipeta incerto. Confira os avisos de impressão nos cartões.</p>}
    {painel.carregando && <p className="rounded-xl bg-panel p-6">Carregando refeições…</p>}
    {!painel.carregando && !painel.indisponivel && <>
      <FiltrosOperacao pedidos={painel.pedidos} filtros={filtros} onChange={setFiltros} total={filtrados.length} />
      <nav aria-label="Etapas da cozinha" className="mb-4 grid grid-cols-3 gap-2 md:hidden">
        {COLUNAS.map((col) => <button key={col.status} onClick={() => setFiltro(col.status)} aria-pressed={filtro === col.status}
          className={`min-h-14 rounded-xl px-2 py-3 text-sm font-semibold ${filtro === col.status ? 'bg-brand text-white' : 'bg-panel'}`}>
          {col.titulo}<span className="ml-1">({filtrados.filter((p) => p.status === col.status).length})</span>
        </button>)}
      </nav>
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-3">
        {COLUNAS.map((col) => {
          const pedidos = filtrados.filter((p) => p.status === col.status)
          return <section key={col.status} className={`min-w-0 rounded-2xl border-t-4 bg-panel p-3 ${col.cor} ${filtro === col.status ? '' : 'hidden md:block'}`}>
            <h2 className="mb-3 text-lg font-bold">{col.titulo} <span className="font-normal text-slate-700">({pedidos.length})</span></h2>
            {!pedidos.length && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-700">Nenhuma refeição nesta etapa.</p>}
            <div className="space-y-3">{pedidos.map((pedido) => <article key={pedido.id} className="rounded-xl bg-white p-4 shadow-sm">
              <ResumoPedido pedido={pedido} />
              <AlertaDemora pedido={pedido} limites={painel.alertas} agora={painel.agora} />
              <EstadoImpressao impressao={pedido.impressao} />
              <EstadoImpressao impressao={pedido.etiqueta} etiqueta />
              <div className="mt-4 flex flex-wrap gap-2">
                {col.status !== 'PRONTO' && <button disabled={ocupados.includes(pedido.id)}
                  onClick={() => agir(pedido, col.status === 'PENDENTE' ? 'EM_PREPARO' : 'PRONTO')}
                  className={`${BOTAO} flex-1 bg-brand text-white hover:bg-brand-hover`}>{col.status === 'PENDENTE' ? 'Iniciar preparo' : 'Marcar pronto'}</button>}
                {col.status === 'PRONTO' && <Link to={`/entregas/${filialId}`} className={`${BOTAO} flex-1 bg-brand-vibrant text-center text-brand-ink hover:bg-brand-vibrant-hover`}>Abrir entregas</Link>}
                <button disabled={ocupados.includes(pedido.id) || ['PENDENTE', 'PROCESSANDO'].includes(pedido.impressao?.estado)} onClick={() => agir(pedido)} className={`${BOTAO} bg-slate-100`} aria-label={`Reimprimir pedido ${pedido.id}`}>{['PENDENTE', 'PROCESSANDO'].includes(pedido.impressao?.estado) ? 'Na fila de impressão' : pedido.impressao?.estado === 'FALHA' ? 'Reenviar filipeta' : 'Reimprimir'}</button>
                {col.status === 'PRONTO' && (pedido.tipo_solicitacao === 'MEDICO' ? pedido.solicitante_nome : pedido.nome_paciente)?.trim() && <button disabled={['PENDENTE', 'PROCESSANDO'].includes(pedido.etiqueta?.estado)} onClick={() => setEtiquetar(pedido)} className={`${BOTAO} bg-brand-soft text-brand-ink`} aria-label={`Etiqueta do pedido ${pedido.id}`}>{['PENDENTE', 'PROCESSANDO'].includes(pedido.etiqueta?.estado) ? 'Etiqueta na fila' : 'Etiqueta'}</button>}
                <button disabled={ocupados.includes(pedido.id)} onClick={() => setCancelar(pedido)} className={`${BOTAO} bg-red-50 text-red-800`} aria-label={`Cancelar pedido ${pedido.id}`}>Cancelar</button>
              </div>
            </article>)}</div>
          </section>
        })}
      </div>
    </>}
    {confirmar && <ConfirmarReenvio pedido={confirmar} onCancelar={() => setConfirmar(null)} onConfirmar={() => { setConfirmar(null); agir(confirmar, null, true) }} />}
    {etiquetar && <EtiquetaPedido cliente={cozinhaApi} prefixo="" filialId={filialId} pedido={etiquetar} onFechar={() => setEtiquetar(null)} onEnfileirada={(mensagem) => { setEtiquetar(null); setAviso(mensagem); painel.recarregar() }} />}
    {cancelar && <CancelarPedido key={cancelar.id} pedido={cancelar}
      disponivel={painel.pedidos.some((p) => p.id === cancelar.id && COLUNAS.some((c) => c.status === p.status)) && !painel.indisponivel}
      onFechar={() => setCancelar(null)} onConfirmar={cancelarPedido} />}
  </main>
}
