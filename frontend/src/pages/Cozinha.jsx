import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../services/api.js'
import { inicioDoUsuario, useAuth } from '../context/auth.js'

const COLUNAS = [
  { status: 'PENDENTE', titulo: '⏳ Pendentes', cor: 'border-t-amber-500' },
  { status: 'EM_PREPARO', titulo: '🍳 Em Preparo', cor: 'border-t-blue-500' },
  { status: 'PRONTO', titulo: '✅ Prontos', cor: 'border-t-emerald-500' },
]

/** Alerta sonoro para novos pedidos (sem ficheiros de áudio — Web Audio API). */
function tocarAlerta() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const ganho = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = 880
    ganho.gain.value = 0.3
    osc.connect(ganho).connect(ctx.destination)
    osc.start()
    setTimeout(() => {
      osc.stop()
      ctx.close()
    }, 400)
  } catch { /* som indisponível */ }
}

export default function Cozinha() {
  const { filialId } = useParams()
  return <PainelCozinha key={filialId} filialId={filialId} />
}

function PainelCozinha({ filialId }) {
  const { usuario, sair } = useAuth()
  const navegar = useNavigate()
  const filiais = usuario.filiais || []
  const filial = filiais.find((f) => f.id === Number(filialId))
  const permitida = Boolean(filial)
  const [pedidos, setPedidos] = useState([])
  const [erro, setErro] = useState(null)

  async function recarregar() {
    if (!permitida) return
    try {
      const r = await api.get('/pedidos', { params: { filial_id: filialId } })
      setPedidos(r.data)
      setErro(null)
    } catch (e) {
      setErro(e.response?.data?.detail || 'Erro ao carregar pedidos')
    }
  }

  useEffect(() => {
    if (!permitida) return
    const controller = new AbortController()
    api.get('/pedidos', { params: { filial_id: filialId }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setPedidos(data) })
      .catch((e) => { if (!controller.signal.aborted) setErro(e.response?.data?.detail || 'Erro ao carregar pedidos') })
    return () => controller.abort()
  }, [filialId, permitida])

  // WebSocket: atualização em tempo real sem F5
  useEffect(() => {
    if (!permitida) return
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
    let encerrado = false
    let ws
    let tentativa
    function conectar() {
      const token = localStorage.getItem('token')
      if (!token || encerrado) return
      ws = new WebSocket(`${protocolo}://${window.location.host}/ws/cozinha/${filialId}`, ['cnutri', token])
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data)
        if (!msg.pedido) return
        if (msg.evento === 'novo_pedido') tocarAlerta()
        setPedidos((atuais) => {
          const novo = msg.pedido
          const idx = atuais.findIndex((p) => p.id === novo.id)
          if (idx === -1) return [novo, ...atuais]
          return atuais.map((p) => p.id === novo.id ? novo : p)
        })
      }
      ws.onclose = (ev) => {
        if (encerrado) return
        if (ev.code === 1008) { setErro('Seu acesso foi atualizado. Entre novamente para continuar.'); return }
        tentativa = setTimeout(conectar, 3000)
      }
    }
    tentativa = setTimeout(conectar, 0)
    return () => { encerrado = true; clearTimeout(tentativa); ws?.close() }
  }, [filialId, permitida])

  async function mover(pedido, novoStatus) {
    try {
      await api.patch(`/pedidos/${pedido.id}/status`, { status: novoStatus })
      setPedidos((atuais) => atuais.map((p) => (p.id === pedido.id ? { ...p, status: novoStatus } : p)))
    } catch (e) {
      setErro(e.response?.data?.detail || 'Erro ao alterar status')
    }
  }

  async function reimprimir(pedido) {
    try {
      const r = await api.post(`/pedidos/${pedido.id}/reimprimir`)
      alert(r.data.impresso ? 'Filipeta enviada à impressora ✅' : 'Impressora não respondeu ⚠️')
    } catch (e) {
      alert(e.response?.data?.detail || 'Erro na reimpressão')
    }
  }

  if (!filial) return <div className="min-h-screen bg-app-background p-6 text-slate-900">
    <div className="max-w-lg space-y-4 rounded-xl bg-panel p-6"><h1 className="text-xl font-bold">Unidade indisponível</h1>
      <p>Seu usuário não possui acesso a esta unidade.</p><Link to={inicioDoUsuario(usuario)} className="underline">Voltar ao painel</Link></div>
  </div>

  return (
    <div className="min-h-screen bg-app-background p-4 text-slate-900">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-bold">🍽️ Cozinha — Painel de Produção</h1><p className="text-sm text-slate-950">{filial.nome}</p></div>
        <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Unidade da cozinha" className="rounded bg-white px-3 py-2 text-sm" value={filialId} onChange={(e) => navegar(`/cozinha/${e.target.value}`)}>
          {filiais.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
        </select>
        {usuario.perfil === 'ADMIN_TI' && <Link to="/admin" className="rounded bg-white px-4 py-2 text-sm">Administração</Link>}
        {usuario.perfil !== 'COZINHA' && <Link to={`/gestao?unidade=${filialId}`} className="rounded bg-white px-4 py-2 text-sm">Gestão</Link>}
        <button onClick={recarregar} className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">
          ↻ Recarregar
        </button>
        <button onClick={sair} className="rounded bg-white px-4 py-2 text-sm">Sair</button>
        </div>
      </header>

      {erro && <div className="mb-4 rounded-lg bg-red-50 p-3 text-red-800">{erro}</div>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {COLUNAS.map((col) => (
          <div key={col.status} className={`rounded-xl bg-panel border-t-4 ${col.cor} p-3`}>
            <h2 className="mb-3 text-lg font-semibold">
              {col.titulo} <span className="text-slate-700">({pedidos.filter((p) => p.status === col.status).length})</span>
            </h2>
            <div className="space-y-3">
              {pedidos
                .filter((p) => p.status === col.status)
                .map((p) => (
                  <CartaoPedido key={p.id} pedido={p} onMover={mover} onReimprimir={reimprimir} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Calcula a idade a partir da data de nascimento (AAAA-MM-DD em dados_dinamicos). */
function calcularIdade(dataISO) {
  if (!dataISO) return null
  const nasc = new Date(dataISO + 'T00:00:00')
  if (isNaN(nasc)) return null
  const hoje = new Date()
  let idade = hoje.getFullYear() - nasc.getFullYear()
  const mes = hoje.getMonth() - nasc.getMonth()
  if (mes < 0 || (mes === 0 && hoje.getDate() < nasc.getDate())) idade--
  return idade >= 0 && idade < 130 ? idade : null
}

function CartaoPedido({ pedido, onMover, onReimprimir }) {
  const severa = pedido.dieta?.severa || /alergi|sever/i.test(pedido.observacoes_alergias || '')
  const idade = calcularIdade(pedido.dados_dinamicos?.data_nascimento)
  const proximo =
    pedido.status === 'PENDENTE' ? 'EM_PREPARO' : pedido.status === 'EM_PREPARO' ? 'PRONTO' : null

  return (
    <div
      className={`rounded-lg p-4 shadow ${severa ? 'bg-red-50 ring-2 ring-red-500' : 'bg-panel'}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <span className="text-xs text-slate-700">#{pedido.id} · {new Date(pedido.criado_em).toLocaleTimeString('pt-BR')}</span>
          <p className="font-bold text-slate-900">
            {pedido.nome_paciente || pedido.solicitante_nome || pedido.solicitante_identificacao}
            {idade !== null && <span className="ml-2 rounded bg-slate-50 px-2 py-0.5 text-xs font-normal text-slate-700">{idade} anos</span>}
          </p>
          <p className="text-sm text-slate-700">
            {pedido.dados_dinamicos?.refeicao && <span className="mr-1 rounded bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">🍽️ {pedido.dados_dinamicos.refeicao}</span>}
            {pedido.dados_dinamicos?.cardapio && <span className="mr-1 rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-800">📋 {pedido.dados_dinamicos.cardapio}</span>}
            {pedido.dados_dinamicos?.liquido_espessado && <span className="mr-1 rounded bg-cyan-100 px-2 py-0.5 text-xs text-cyan-800">🥤 {pedido.dados_dinamicos.liquido_espessado}</span>}
            {pedido.dados_dinamicos?.para && <span className="mr-1 rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-700">para: {pedido.dados_dinamicos.para}</span>}
          </p>
          <p className="text-sm text-slate-700">
            {pedido.leito && <>🛏️ Leito {pedido.leito} · </>}
            {pedido.dados_dinamicos?.andar && <>🏢 {pedido.dados_dinamicos.andar} · </>}
            {pedido.dieta ? pedido.dieta.nome : '—'}
          </p>
        </div>
        {severa && <span className="rounded bg-red-600 px-2 py-1 text-xs font-bold text-white">⚠️ SEVERO</span>}
      </div>
      {pedido.observacoes_alergias && (
        <p className="mt-2 text-sm text-amber-800">⚠️ {pedido.observacoes_alergias}</p>
      )}
      <div className="mt-3 flex gap-2">
        {proximo && (
          <button
            onClick={() => onMover(pedido, proximo)}
            className="flex-1 rounded bg-blue-600 px-3 py-2 text-sm font-medium hover:bg-blue-500 text-white"
          >
            → {proximo === 'EM_PREPARO' ? 'Iniciar preparo' : 'Marcar pronto'}
          </button>
        )}
        <button
          onClick={() => onReimprimir(pedido)}
          className="rounded bg-slate-200 px-3 py-2 text-sm hover:bg-slate-300"
          title="Reimprimir filipeta"
        >
          🖨️
        </button>
        {pedido.status !== 'CANCELADO' && (
          <button
            onClick={() => onMover(pedido, 'CANCELADO')}
            className="rounded bg-slate-50 px-3 py-2 text-sm text-red-800 hover:bg-slate-200"
            title="Cancelar pedido"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}
