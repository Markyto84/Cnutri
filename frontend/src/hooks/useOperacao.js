import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'

export const operacao = axios.create({ baseURL: '/api/operacao' })
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
  const [filiais, setFiliais] = useState([])
  const [pedidos, setPedidos] = useState([])
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [indisponivel, setIndisponivel] = useState(false)
  const [conectado, setConectado] = useState(false)
  const revisao = useRef(0)
  const montado = useRef(false)
  const filial = filiais.find((f) => f.id === Number(filialId))
  const filialDisponivel = Boolean(filial)

  const aplicarPedido = useCallback((pedido) => {
    revisao.current++
    setPedidos((atuais) => {
      if (!ETAPAS.includes(pedido.status)) return atuais.filter((p) => p.id !== pedido.id)
      return atuais.some((p) => p.id === pedido.id)
        ? atuais.map((p) => p.id === pedido.id ? pedido : p) : [...atuais, pedido]
    })
  }, [])

  const recarregar = useCallback(async (signal) => {
    const versao = revisao.current
    try {
      const [unidades, lista] = await Promise.all([
        operacao.get('/unidades', { signal }),
        operacao.get(`/unidades/${filialId}/pedidos`, { signal }),
      ])
      if (signal?.aborted || !montado.current) return
      setFiliais(unidades.data)
      if (versao === revisao.current) setPedidos(lista.data)
      setIndisponivel(false)
      setErro(null)
    } catch (e) {
      if (signal?.aborted || !montado.current) return
      setErro(e.response?.data?.detail || 'Sem conexão. Tentando atualizar o painel…')
      if ([404, 422].includes(e.response?.status)) { setIndisponivel(true); setPedidos([]) }
    } finally { if (!signal?.aborted && montado.current) setCarregando(false) }
  }, [filialId])

  useEffect(() => {
    montado.current = true
    const controller = new AbortController()
    const inicial = setTimeout(() => recarregar(controller.signal), 0)
    const intervalo = setInterval(() => recarregar(controller.signal), 10000)
    return () => { montado.current = false; controller.abort(); clearTimeout(inicial); clearInterval(intervalo) }
  }, [recarregar])

  useEffect(() => {
    if (!filialDisponivel || indisponivel) return
    const protocolo = window.location.protocol === 'https:' ? 'wss' : 'ws'
    let encerrado = false
    let ws, tentativa
    function conectar() {
      if (encerrado) return
      ws = new WebSocket(`${protocolo}://${window.location.host}/ws/operacao/${filialId}`)
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
        if (code === 1008) { setIndisponivel(true); setPedidos([]); setErro('Unidade indisponível'); return }
        tentativa = setTimeout(conectar, 3000)
      }
    }
    conectar()
    return () => { encerrado = true; clearTimeout(tentativa); ws?.close() }
  }, [filialDisponivel, filialId, indisponivel, som, aplicarPedido, recarregar])

  return { filial, filiais, pedidos, erro, setErro, carregando, indisponivel, conectado, recarregar, aplicarPedido }
}
