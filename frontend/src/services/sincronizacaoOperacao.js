// Estado clínico permanece apenas na memória da tela e é descartado ao trocar de sessão.
export const RECONCILIACAO_MS = 120000
export const PULSO_MS = 25000
const ETAPAS = ['PENDENTE', 'EM_PREPARO', 'PRONTO']

export function atualizarPedidos(pedidos, pedido) {
  if (!ETAPAS.includes(pedido.status)) return pedidos.filter((p) => p.id !== pedido.id)
  return pedidos.some((p) => p.id === pedido.id)
    ? pedidos.map((p) => p.id === pedido.id ? pedido : p) : [...pedidos, pedido]
}

function ambienteBrowser() {
  return {
    agendar: (fn, ms) => setTimeout(fn, ms), cancelar: (id) => clearTimeout(id),
    agora: () => Date.now(), aleatorio: () => Math.random(),
    online: () => navigator.onLine !== false, visivel: () => !document.hidden,
    escutar: (nome, fn) => {
      const alvo = nome === 'visibilitychange' ? document : window
      alvo.addEventListener(nome, fn)
      return () => alvo.removeEventListener(nome, fn)
    },
  }
}

export function criarSincronizacaoOperacao({ filialId, token, entregas = false, consultar, criarSocket,
  onEstado, onMensagem, onConexao, onErro, onBloqueio, onCarregado, ambiente = ambienteBrowser() }) {
  let encerrado = false, bloqueado = false, conectado = false, socket = null
  let consulta = null, controller = null, etag = null, eventos = []
  let timerConsulta, timerConexao, timerPulso, falhas = 0, tentativas = 0
  let ultimaMensagem = ambiente.agora(), ultimaConsulta = -Infinity, repetirAposConsulta = false
  const remover = []
  const cancelar = (timer) => { if (timer !== undefined) ambiente.cancelar(timer) }
  const jitter = (ms) => Math.round(ms * (0.9 + ambiente.aleatorio() * 0.2))

  function agendarConsulta(ms) {
    cancelar(timerConsulta)
    if (!encerrado && !bloqueado && ambiente.online()) timerConsulta = ambiente.agendar(() => recarregar(), ms)
  }

  function receber(msg) {
    if (encerrado || bloqueado) return
    if (consulta) eventos.push(msg)
    onMensagem(msg)
  }

  function bloquear(mensagem) {
    bloqueado = true; conectado = false; etag = null; eventos = []
    cancelar(timerConsulta); cancelar(timerConexao); cancelar(timerPulso)
    controller?.abort()
    if (socket) { socket.onclose = null; socket.close(); socket = null }
    onConexao(false); onBloqueio(true); onErro(mensagem); onCarregado()
  }

  async function executarConsulta() {
    controller = new AbortController()
    eventos = []
    try {
      const resposta = await consultar({ signal: controller.signal, etag })
      if (encerrado || bloqueado || controller.signal.aborted) return
      if (resposta.status !== 304) {
        onEstado(resposta.data)
        // Reaplica eventos que chegaram durante o HTTP, inclusive remoções por entrega.
        for (const msg of eventos) onMensagem(msg, true)
      }
      etag = resposta.headers?.etag || null
      falhas = 0; ultimaConsulta = ambiente.agora()
      onBloqueio(false); onErro(null)
    } catch (e) {
      if (encerrado || bloqueado || controller.signal.aborted) return
      if ([401, 403, 404, 422].includes(e.response?.status)) {
        bloquear(e.response?.data?.detail || 'Acesso encerrado. Atualize sua sessão.')
        return
      }
      falhas++
      onErro(e.response?.data?.detail || 'Sem conexão. Tentando atualizar o painel…')
    } finally {
      eventos = []; controller = null
      if (!encerrado && !bloqueado) onCarregado()
    }
  }

  function recarregar(manual = false) {
    if (encerrado || !ambiente.online()) return Promise.resolve()
    if (manual && bloqueado) { bloqueado = false; onBloqueio(false); conectar() }
    if (bloqueado) return Promise.resolve()
    if (consulta) return consulta
    cancelar(timerConsulta)
    if (conectado && !manual && !ambiente.visivel()) {
      agendarConsulta(jitter(RECONCILIACAO_MS))
      return Promise.resolve()
    }
    consulta = executarConsulta().finally(() => {
      consulta = null
      if (encerrado || bloqueado) return
      if (repetirAposConsulta) {
        repetirAposConsulta = false; agendarConsulta(0)
      } else {
        const intervalo = falhas ? Math.min(60000, (entregas ? 5000 : 10000) * 2 ** (falhas - 1))
          : conectado ? RECONCILIACAO_MS : entregas ? 5000 : 10000
        agendarConsulta(falhas ? Math.min(60000, jitter(intervalo)) : jitter(intervalo))
      }
    })
    return consulta
  }

  function agendarConexao() {
    cancelar(timerConexao)
    if (encerrado || bloqueado || !ambiente.online()) return
    const demora = Math.min(30000, 1000 * 2 ** Math.min(tentativas++, 5))
    timerConexao = ambiente.agendar(conectar, Math.min(30000, jitter(demora)))
  }

  function pulsar() {
    cancelar(timerPulso)
    if (encerrado || !conectado || !socket) return
    const limite = ambiente.visivel() ? 60000 : 180000
    if (ambiente.agora() - ultimaMensagem > limite) {
      perderConexao()
      return
    }
    try { socket.send('ping') } catch { perderConexao(); return }
    timerPulso = ambiente.agendar(pulsar, PULSO_MS)
  }

  function perderConexao() {
    const estavaConectado = conectado
    const anterior = socket
    socket = null; conectado = false
    cancelar(timerPulso)
    if (anterior) { anterior.onclose = null; anterior.close() }
    onConexao(false)
    if (estavaConectado) agendarConsulta(0)
    agendarConexao()
  }

  function conectar() {
    if (encerrado || bloqueado || !ambiente.online() || socket) return
    cancelar(timerConexao)
    let atual
    try { atual = criarSocket(filialId, token); socket = atual }
    catch { agendarConexao(); return }
    atual.onopen = () => {
      if (encerrado || socket !== atual) return
      cancelar(timerConexao)
      conectado = true; tentativas = 0; ultimaMensagem = ambiente.agora()
      onConexao(true); cancelar(timerConsulta)
      // Se um HTTP começou antes da conexão, outro snapshot fecha a janela sem eventos.
      if (consulta) repetirAposConsulta = true
      else recarregar(true)
      pulsar()
    }
    atual.onmessage = ({ data }) => {
      if (encerrado || bloqueado || socket !== atual) return
      ultimaMensagem = ambiente.agora()
      try {
        const msg = JSON.parse(data)
        if (msg.evento !== 'pong') receber(msg)
      } catch { agendarConsulta(0) }
    }
    atual.onclose = ({ code }) => {
      if (encerrado || socket !== atual) return
      const estavaConectado = conectado
      socket = null; conectado = false; cancelar(timerPulso); cancelar(timerConexao); onConexao(false)
      if (code === 1008) { bloquear(token ? 'Acesso encerrado. Atualize sua sessão.' : 'Unidade indisponível'); return }
      if (estavaConectado) agendarConsulta(0)
      agendarConexao()
    }
    // Evita ficar preso em uma abertura que nunca conclui.
    timerConexao = ambiente.agendar(() => { if (socket === atual && !conectado) perderConexao() }, 10000)
  }

  function retomar() {
    if (encerrado || bloqueado || !ambiente.online() || !ambiente.visivel()) return
    if (conectado && ambiente.agora() - ultimaMensagem > 60000) perderConexao()
    conectar()
    if (ambiente.agora() - ultimaConsulta > 1000) {
      if (consulta) repetirAposConsulta = true
      recarregar(true)
    }
  }

  return {
    iniciar() {
      conectar(); agendarConsulta(1000)
      if (!ambiente.online()) { onErro('Sem conexão. A atualização será retomada automaticamente.'); onCarregado() }
      remover.push(ambiente.escutar('online', retomar), ambiente.escutar('focus', retomar),
        ambiente.escutar('visibilitychange', retomar), ambiente.escutar('offline', () => {
          cancelar(timerConsulta); cancelar(timerConexao); cancelar(timerPulso)
          controller?.abort()
          perderConexao()
          onErro('Sem conexão. A atualização será retomada automaticamente.')
        }))
    },
    recarregar,
    aplicarPedido(pedido) { receber({ pedido }) },
    parar() {
      encerrado = true; eventos = []; etag = null
      cancelar(timerConsulta); cancelar(timerConexao); cancelar(timerPulso)
      controller?.abort(); remover.forEach((fn) => fn())
      if (socket) { socket.onclose = null; socket.close(); socket = null }
    },
  }
}
