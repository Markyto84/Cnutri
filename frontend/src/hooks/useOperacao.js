import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../services/api.js'
import { useAuth } from '../context/auth.js'
import { atualizarPedidos, criarSincronizacaoOperacao } from '../services/sincronizacaoOperacao.js'

export const operacao = { get: (url, config) => api.get(`/operacao${url}`, config) }
const INICIAL = { filiais: [], pedidos: [], copeiras: [], alertas: { preparo_minutos: 30, entrega_minutos: 30 },
  erro: null, carregando: true, indisponivel: false, conectado: false }

function tocarAlerta() {
  try {
    const ctx = new AudioContext(), osc = ctx.createOscillator(), ganho = ctx.createGain()
    osc.frequency.value = 880; ganho.gain.value = 0.2
    osc.connect(ganho).connect(ctx.destination); osc.start()
    setTimeout(() => { osc.stop(); ctx.close() }, 400)
  } catch { /* áudio depende das permissões do navegador */ }
}

export function useOperacao(filialId, som = false, entregas = false) {
  const { usuario, carregando: acessoCarregando } = useAuth()
  const token = localStorage.getItem('token')
  const escopo = `${filialId}:${usuario?.id || ''}:${token || ''}`
  const [consulta, setConsulta] = useState({ ...INICIAL, escopo: '' })
  const estado = consulta.escopo === escopo ? consulta : INICIAL
  const [agora, setAgora] = useState(Date.now)
  const sincronizacao = useRef(null)

  useEffect(() => {
    if (acessoCarregando) return
    const atualizar = (fn) => setConsulta((anterior) => fn(anterior.escopo === escopo ? anterior : { ...INICIAL, escopo }))
    const sync = criarSincronizacaoOperacao({
      filialId, token, entregas,
      consultar: ({ signal, etag }) => operacao.get(`/unidades/${filialId}/estado`, {
        signal, timeout: 10000, headers: etag ? { 'If-None-Match': etag } : {},
        validateStatus: (status) => status === 200 || status === 304,
      }),
      criarSocket: (id, credencial) => {
        const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
        return credencial ? new WebSocket(`${protocolo}://${window.location.host}/ws/cozinha/${id}`, ['cnutri', credencial])
          : new WebSocket(`${protocolo}://${window.location.host}/ws/operacao/${id}`)
      },
      onEstado: ({ unidades, ...dados }) => atualizar((s) => ({ ...s, ...dados, filiais: unidades })),
      onMensagem: (msg, repetida) => {
        if (som && !repetida && msg.evento === 'novo_pedido') tocarAlerta()
        atualizar((s) => ({ ...s, ...(msg.unidades ? { filiais: msg.unidades } : {}),
          ...(msg.alertas ? { alertas: msg.alertas } : {}), ...(msg.copeiras ? { copeiras: msg.copeiras } : {}),
          ...(msg.pedido ? { pedidos: atualizarPedidos(s.pedidos, msg.pedido) } : {}) }))
      },
      onConexao: (conectado) => atualizar((s) => ({ ...s, conectado })),
      onErro: (erro) => atualizar((s) => ({ ...s, erro })),
      onBloqueio: (indisponivel) => atualizar((s) => ({ ...s, indisponivel, ...(indisponivel ? { pedidos: [], copeiras: [] } : {}) })),
      onCarregado: () => { setAgora(Date.now()); atualizar((s) => ({ ...s, carregando: false })) },
    })
    sincronizacao.current = sync
    sync.iniciar()
    const relogio = setInterval(() => setAgora(Date.now()), 30000)
    return () => { sync.parar(); clearInterval(relogio); if (sincronizacao.current === sync) sincronizacao.current = null }
  }, [escopo, filialId, token, som, entregas, acessoCarregando])

  const recarregar = useCallback(() => sincronizacao.current?.recarregar(true), [])
  const aplicarPedido = useCallback((pedido) => sincronizacao.current?.aplicarPedido(pedido), [])
  const setErro = useCallback((erro) => setConsulta((s) => ({ ...s, erro })), [])
  return { ...estado, filial: estado.filiais.find((f) => f.id === Number(filialId)), agora, recarregar, aplicarPedido, setErro }
}
