import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../services/api.js'
import { useAuth } from '../context/auth.js'

export const operacao = { get: (url, config) => api.get(`/operacao${url}`, config) }
const ETAPAS = ['PENDENTE', 'EM_PREPARO', 'PRONTO']

function tocarAlerta() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const ganho = ctx.createGain()
    osc.frequency.value = 880
    ganho.gain.value = 0.2
    osc.connect(ganho).connect(ctx.destination)
    osc.start()
    setTimeout(() => { osc.stop(); ctx.close() }, 400)
  } catch { /* áudio depende das permissões do navegador */ }
}

export function useOperacao(filialId, som = false) {
  const { usuario } = useAuth()
  const token = localStorage.getItem('token')
  const escopo = `${filialId}:${usuario?.id || ''}:${token || ''}`
  const [filiais, setFiliais] = useState([])
  const [consulta, setConsulta] = useState({ escopo: '', pedidos: [] })
  const pedidos = consulta.escopo === escopo ? consulta.pedidos : []
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [indisponivel, setIndisponivel] = useState(false)
  const [conectado, setConectado] = useState(false)
  const [alertas, setAlertas] = useState({ preparo_minutos: 30, entrega_minutos: 30 })
  const [agora, setAgora] = useState(Date.now)
  const revisao = useRef(0)
  const montado = useRef(false)
  const filial = filiais.find((f) => f.id === Number(filialId))
  const filialDisponivel = Boolean(filial)

  const aplicarPedido = useCallback((pedido) => {
    revisao.current++
    setConsulta((anterior) => {
      const atuais = anterior.escopo === escopo ? anterior.pedidos : []
      const lista = !ETAPAS.includes(pedido.status) ? atuais.filter((p) => p.id !== pedido.id)
        : atuais.some((p) => p.id === pedido.id) ? atuais.map((p) => p.id === pedido.id ? pedido : p) : [...atuais, pedido]
      return { escopo, pedidos: lista }
    })
  }, [escopo])

  const recarregar = useCallback(async (signal) => {
    const versao = revisao.current
    try {
      const [unidades, lista, prazos] = await Promise.all([
        operacao.get('/unidades', { signal }),
        operacao.get(`/unidades/${filialId}/pedidos`, { signal }),
        operacao.get(`/unidades/${filialId}/alertas`, { signal }).catch(() => null),
      ])
      if (signal?.aborted || !montado.current) return
      setFiliais(unidades.data)
      if (prazos) setAlertas(prazos.data)
      setAgora(Date.now())
      if (versao === revisao.current) setConsulta({ escopo, pedidos: lista.data })
      setIndisponivel(false)
      setErro(null)
    } catch (e) {
      if (signal?.aborted || !montado.current) return
      setErro(e.response?.data?.detail || 'Sem conexão. Tentando atualizar o painel…')
      if ([401, 403, 404, 422].includes(e.response?.status)) { setIndisponivel(true); setConsulta({ escopo, pedidos: [] }) }
    } finally { if (!signal?.aborted && montado.current) setCarregando(false) }
  }, [filialId, escopo])

  useEffect(() => {
    montado.current = true
    const controller = new AbortController()
    const inicial = setTimeout(() => recarregar(controller.signal), 0)
    const intervalo = setInterval(() => recarregar(controller.signal), 10000)
    const relogio = setInterval(() => setAgora(Date.now()), 30000)
    return () => { montado.current = false; controller.abort(); clearTimeout(inicial); clearInterval(intervalo); clearInterval(relogio) }
  }, [recarregar])

  useEffect(() => {
    if (!filialDisponivel || indisponivel) return
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
    let encerrado = false
    let ws, tentativa
    function conectar() {
      if (encerrado) return
      ws = token ? new WebSocket(`${protocolo}://${window.location.host}/ws/cozinha/${filialId}`, ['cnutri', token])
        : new WebSocket(`${protocolo}://${window.location.host}/ws/operacao/${filialId}`)
      ws.onopen = () => { setConectado(true); recarregar() }
      ws.onmessage = ({ data }) => {
        try {
          const msg = JSON.parse(data)
          if (msg.pedido) {
            if (som && msg.evento === 'novo_pedido') tocarAlerta()
            aplicarPedido(msg.pedido)
          }
        } catch { /* ignora mensagens sem dados de pedido */ }
      }
      ws.onclose = ({ code }) => {
        if (encerrado) return
        setConectado(false)
        if (code === 1008) { setIndisponivel(true); setConsulta({ escopo, pedidos: [] }); setErro(token ? 'Acesso encerrado. Atualize sua sessão.' : 'Unidade indisponível'); return }
        tentativa = setTimeout(conectar, 3000)
      }
    }
    conectar()
    return () => { encerrado = true; clearTimeout(tentativa); ws?.close() }
  }, [filialDisponivel, filialId, indisponivel, som, aplicarPedido, recarregar, token, escopo])

  return { filial, filiais, pedidos, alertas, agora, erro, setErro, carregando, indisponivel, conectado, recarregar, aplicarPedido }
}
