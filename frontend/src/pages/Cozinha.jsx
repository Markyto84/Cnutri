import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../services/api.js'

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
  const [pedidos, setPedidos] = useState([])
  const [erro, setErro] = useState(null)
  const wsRef = useRef(null)

  const recarregar = useCallback(async () => {
    try {
      const r = await api.get('/pedidos', { params: { filial_id: filialId } })
      setPedidos(r.data)
    } catch (e) {
      setErro(e.response?.data?.detail || 'Erro ao carregar pedidos')
    }
  }, [filialId])

  useEffect(() => {
    recarregar()
  }, [recarregar])

  // WebSocket: atualização em tempo real sem F5
  useEffect(() => {
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocolo}://${window.location.host}/ws/cozinha/${filialId}`)
    wsRef.current = ws
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.evento === 'novo_pedido') tocarAlerta()
      setPedidos((atuais) => {
        const novo = msg.pedido
        const idx = atuais.findIndex((p) => p.id === novo.id)
        if (idx === -1) return [novo, ...atuais]
        const copia = [...atuais]
        copia[idx] = novo
        return copia
      })
    }
    ws.onclose = () => setTimeout(() => window.location.reload(), 3000) // reconexão simples
    return () => ws.close()
  }, [filialId])

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

  return (
    <div className="min-h-screen bg-app-background p-4 text-slate-900">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">🍽️ Cozinha — Painel de Produção</h1>
        <button onClick={recarregar} className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">
          ↻ Recarregar
        </button>
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
