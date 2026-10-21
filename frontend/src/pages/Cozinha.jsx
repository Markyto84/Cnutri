import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useOperacao } from '../hooks/useOperacao.js'
import { api } from '../services/api.js'
import { podeOperar, useAuth } from '../context/auth.js'
import { BOTAO, CabecalhoOperacao, ResumoPedido } from '../components/Operacao.jsx'

const COLUNAS = [
  { status: 'PENDENTE', titulo: 'Pendentes', cor: 'border-t-amber-500' },
  { status: 'EM_PREPARO', titulo: 'Em preparo', cor: 'border-t-brand' },
  { status: 'PRONTO', titulo: 'Prontos', cor: 'border-t-emerald-600' },
]

export default function Cozinha() {
  const { filialId } = useParams()
  return <Dashboard key={filialId} filialId={filialId} />
}

function Dashboard({ filialId }) {
  const painel = useOperacao(filialId, true)
  const { usuario } = useAuth()
  const autorizado = podeOperar(usuario, filialId, ['COZINHA', 'NUTRICIONISTA', 'ADMIN_TI'])
  const [filtro, setFiltro] = useState('PENDENTE')
  const [ocupados, setOcupados] = useState([])
  const [aviso, setAviso] = useState('')

  async function agir(pedido, status) {
    if (!autorizado || ocupados.includes(pedido.id)) return
    setOcupados((atuais) => [...atuais, pedido.id])
    setAviso('')
    try {
      const base = `/operacao/unidades/${filialId}/pedidos/${pedido.id}`
      if (status) {
        const { data } = await api.patch(base + '/status', { status })
        painel.aplicarPedido(data)
      } else {
        const { data } = await api.post(base + '/reimprimir')
        setAviso(data.impresso ? `Filipeta do pedido #${pedido.id} enviada à impressora.` : 'A impressora não respondeu.')
      }
    } catch (e) {
      painel.setErro(e.response?.data?.detail || 'Não foi possível atualizar o pedido')
    } finally { setOcupados((atuais) => atuais.filter((id) => id !== pedido.id)) }
  }

  return <main className="min-h-screen bg-app-background p-3 text-slate-900 sm:p-5">
    <CabecalhoOperacao modo="cozinha" painel={painel} filialId={filialId} />
    {!autorizado && <p className="mb-4 rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Painel em modo de consulta. Entre com um perfil de cozinha ou gestão autorizado nesta unidade para operar os pedidos.</p>}
    {painel.erro && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-900">{painel.erro}</p>}
    {aviso && <p role="status" className="mb-4 rounded-lg bg-brand-soft p-3 text-brand-ink">{aviso}</p>}
    {painel.carregando && <p className="rounded-xl bg-panel p-6">Carregando refeições…</p>}
    {!painel.carregando && !painel.indisponivel && <>
      <nav aria-label="Etapas da cozinha" className="mb-4 grid grid-cols-3 gap-2 md:hidden">
        {COLUNAS.map((col) => <button key={col.status} onClick={() => setFiltro(col.status)} aria-pressed={filtro === col.status}
          className={`min-h-14 rounded-xl px-2 py-3 text-sm font-semibold ${filtro === col.status ? 'bg-brand text-white' : 'bg-panel'}`}>
          {col.titulo}<span className="ml-1">({painel.pedidos.filter((p) => p.status === col.status).length})</span>
        </button>)}
      </nav>
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-3">
        {COLUNAS.map((col) => {
          const pedidos = painel.pedidos.filter((p) => p.status === col.status)
          return <section key={col.status} className={`min-w-0 rounded-2xl border-t-4 bg-panel p-3 ${col.cor} ${filtro === col.status ? '' : 'hidden md:block'}`}>
            <h2 className="mb-3 text-lg font-bold">{col.titulo} <span className="font-normal text-slate-700">({pedidos.length})</span></h2>
            {!pedidos.length && <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-700">Nenhuma refeição nesta etapa.</p>}
            <div className="space-y-3">{pedidos.map((pedido) => <article key={pedido.id} className="rounded-xl bg-white p-4 shadow-sm">
              <ResumoPedido pedido={pedido} />
              <div className="mt-4 flex flex-wrap gap-2">
                {autorizado && col.status !== 'PRONTO' && <button disabled={ocupados.includes(pedido.id)} onClick={() => agir(pedido, col.status === 'PENDENTE' ? 'EM_PREPARO' : 'PRONTO')}
                  className={`${BOTAO} flex-1 bg-brand text-white hover:bg-brand-hover`}>{col.status === 'PENDENTE' ? 'Iniciar preparo' : 'Marcar pronto'}</button>}
                {col.status === 'PRONTO' && <Link to={`/entregas/${filialId}`} className={`${BOTAO} flex-1 bg-brand-vibrant text-center text-brand-ink hover:bg-brand-vibrant-hover`}>Abrir entregas</Link>}
                {autorizado && <button disabled={ocupados.includes(pedido.id)} onClick={() => agir(pedido)} className={`${BOTAO} bg-slate-100`} aria-label={`Reimprimir pedido ${pedido.id}`}>Reimprimir</button>}
                {autorizado && <button disabled={ocupados.includes(pedido.id)} onClick={() => agir(pedido, 'CANCELADO')} className={`${BOTAO} bg-red-50 text-red-800`} aria-label={`Cancelar pedido ${pedido.id}`}>Cancelar</button>}
              </div>
            </article>)}</div>
          </section>
        })}
      </div>
    </>}
  </main>
}
