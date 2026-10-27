import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useOperacao } from '../hooks/useOperacao.js'
import { api } from '../services/api.js'
import { podeOperar, useAuth } from '../context/auth.js'
import { BOTAO, CabecalhoOperacao, ResumoPedido } from '../components/Operacao.jsx'
import { ConfirmarReenvio, EstadoImpressao } from '../components/ImpressaoPedido.jsx'
import EtiquetaPedido from '../components/EtiquetaPedido.jsx'
import FiltrosOperacao from '../components/FiltrosOperacao.jsx'
import AlertaDemora from '../components/AlertaDemora.jsx'
import CancelarPedido from '../components/CancelarPedido.jsx'
import { FILTROS_VAZIOS, filtrarPedidos } from '../services/painelOperacional.js'

const COLUNAS = [
  { status: 'PENDENTE', titulo: 'Pendentes', cor: 'border-t-amber-500' },
  { status: 'EM_PREPARO', titulo: 'Em preparo', cor: 'border-t-brand' },
  { status: 'PRONTO', titulo: 'Prontos', cor: 'border-t-emerald-600' },
]

export default function Cozinha() {
  const { filialId } = useParams()
  const { usuario } = useAuth()
  return <Dashboard key={`${filialId}:${usuario?.id || 'publico'}`} filialId={filialId} />
}

function Dashboard({ filialId }) {
  const painel = useOperacao(filialId, true)
  const { usuario, carregando: acessoCarregando } = useAuth()
  const autorizado = podeOperar(usuario, filialId, ['COZINHA', 'NUTRICIONISTA', 'ADMIN_TI'])
  const retorno = encodeURIComponent(`/cozinha/${filialId}`)
  const motivoBloqueio = acessoCarregando ? 'Conferindo o acesso à cozinha…'
    : !usuario ? 'Entre com uma conta da Cozinha, Nutrição ou Administração de TI para iniciar o preparo e marcar refeições como prontas.'
      : usuario.troca_senha_obrigatoria ? 'Conclua a troca da senha temporária para liberar as ações da cozinha.'
        : usuario.perfil === 'COPEIRA' ? 'Você está conectado como Copeira. Este perfil realiza entregas; o preparo é operado por Cozinha, Nutrição ou Administração de TI.'
          : 'Sua conta não possui permissão para operar a cozinha desta unidade. Selecione uma unidade vinculada à sua conta ou entre com outra conta autorizada.'
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
    if (!autorizado || ocupados.includes(pedido.id)) return
    if (!status && pedido.impressao?.estado === 'INCERTO' && !riscoConfirmado) { setConfirmar(pedido); return }
    setOcupados((atuais) => [...atuais, pedido.id])
    setAviso('')
    try {
      const base = `/operacao/unidades/${filialId}/pedidos/${pedido.id}`
      if (status) {
        const { data } = await api.patch(base + '/status', { status })
        painel.aplicarPedido(data)
      } else {
        const { data } = await api.post(base + '/reimprimir', { confirmar_risco_duplicidade: riscoConfirmado })
        setAviso(data.enfileirado ? `Filipeta do pedido #${pedido.id} adicionada à fila.` : data.impressao?.erro || 'Não foi possível preparar a impressão.')
        await painel.recarregar()
      }
    } catch (e) {
      painel.setErro(e.response?.data?.detail || 'Não foi possível atualizar o pedido')
    } finally { setOcupados((atuais) => atuais.filter((id) => id !== pedido.id)) }
  }

  async function cancelarPedido(motivo) {
    if (!autorizado || !cancelar) throw new Error('Cancelamento indisponível')
    const { data } = await api.patch(`/operacao/unidades/${filialId}/pedidos/${cancelar.id}/status`, { status: 'CANCELADO', motivo })
    painel.aplicarPedido(data)
    setAviso(`Pedido #${cancelar.id} cancelado. Motivo registrado no relatório.`)
  }

  return <main className="min-h-screen bg-app-background p-3 text-slate-900 sm:p-5">
    <CabecalhoOperacao modo="cozinha" painel={painel} filialId={filialId} />
    {!autorizado && <div id="acesso-cozinha" role="status" className="mb-4 space-y-3 rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">
      <p>{motivoBloqueio}</p>
      {!acessoCarregando && <div className="flex flex-wrap gap-2">
        <Link to={usuario?.troca_senha_obrigatoria ? `/senha?retorno=${retorno}` : `/login?retorno=${retorno}`}
          className={`${BOTAO} bg-brand text-white hover:bg-brand-hover`}>
          {usuario?.troca_senha_obrigatoria ? 'Definir nova senha' : usuario ? 'Entrar com conta da cozinha' : 'Entrar para operar a cozinha'}
        </Link>
        {usuario?.perfil === 'COPEIRA' && <Link to={`/entregas/${filialId}`} className={`${BOTAO} bg-white`}>Realizar entregas</Link>}
      </div>}
    </div>}
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
                {col.status !== 'PRONTO' && <button disabled={!autorizado || acessoCarregando || ocupados.includes(pedido.id)}
                  aria-describedby={!autorizado ? 'acesso-cozinha' : undefined} title={!autorizado ? motivoBloqueio : undefined}
                  onClick={() => agir(pedido, col.status === 'PENDENTE' ? 'EM_PREPARO' : 'PRONTO')}
                  className={`${BOTAO} flex-1 bg-brand text-white hover:bg-brand-hover`}>{col.status === 'PENDENTE' ? 'Iniciar preparo' : 'Marcar pronto'}</button>}
                {col.status === 'PRONTO' && <Link to={`/entregas/${filialId}`} className={`${BOTAO} flex-1 bg-brand-vibrant text-center text-brand-ink hover:bg-brand-vibrant-hover`}>Abrir entregas</Link>}
                {autorizado && <button disabled={ocupados.includes(pedido.id) || ['PENDENTE', 'PROCESSANDO'].includes(pedido.impressao?.estado)} onClick={() => agir(pedido)} className={`${BOTAO} bg-slate-100`} aria-label={`Reimprimir pedido ${pedido.id}`}>{['PENDENTE', 'PROCESSANDO'].includes(pedido.impressao?.estado) ? 'Na fila de impressão' : pedido.impressao?.estado === 'FALHA' ? 'Reenviar filipeta' : 'Reimprimir'}</button>}
                {autorizado && col.status === 'PRONTO' && (pedido.tipo_solicitacao === 'MEDICO' ? pedido.solicitante_nome : pedido.nome_paciente)?.trim() && <button disabled={['PENDENTE', 'PROCESSANDO'].includes(pedido.etiqueta?.estado)} onClick={() => setEtiquetar(pedido)} className={`${BOTAO} bg-brand-soft text-brand-ink`} aria-label={`Etiqueta do pedido ${pedido.id}`}>{['PENDENTE', 'PROCESSANDO'].includes(pedido.etiqueta?.estado) ? 'Etiqueta na fila' : 'Etiqueta'}</button>}
                {autorizado && <button disabled={ocupados.includes(pedido.id)} onClick={() => setCancelar(pedido)} className={`${BOTAO} bg-red-50 text-red-800`} aria-label={`Cancelar pedido ${pedido.id}`}>Cancelar</button>}
              </div>
            </article>)}</div>
          </section>
        })}
      </div>
    </>}
    {confirmar && <ConfirmarReenvio pedido={confirmar} onCancelar={() => setConfirmar(null)} onConfirmar={() => { setConfirmar(null); agir(confirmar, null, true) }} />}
    {autorizado && etiquetar && <EtiquetaPedido filialId={filialId} pedido={etiquetar} onFechar={() => setEtiquetar(null)} onEnfileirada={(mensagem) => { setEtiquetar(null); setAviso(mensagem); painel.recarregar() }} />}
    {autorizado && cancelar && <CancelarPedido key={cancelar.id} pedido={cancelar}
      disponivel={painel.pedidos.some((p) => p.id === cancelar.id && COLUNAS.some((c) => c.status === p.status)) && !painel.indisponivel}
      onFechar={() => setCancelar(null)} onConfirmar={cancelarPedido} />}
  </main>
}
