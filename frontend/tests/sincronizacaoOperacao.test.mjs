import test from 'node:test'
import assert from 'node:assert/strict'
import { atualizarPedidos, criarSincronizacaoOperacao } from '../src/services/sincronizacaoOperacao.js'

const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve() }
const resposta = (pedidos = [], etag = '"v1"') => ({ status: 200, data: {
  unidades: [{ id: 1, nome: 'Unidade teste' }], alertas: { preparo_minutos: 30, entrega_minutos: 30 }, pedidos, copeiras: [],
}, headers: { etag } })

function montar({ consultar, entregas = true, online = true } = {}) {
  let tempo = 0, visivel = true, rede = online, proximo = 0
  const timers = new Map(), ouvintes = new Map(), sockets = [], chamadas = [], erros = []
  const ambiente = {
    agora: () => tempo, aleatorio: () => 0.5, online: () => rede, visivel: () => visivel,
    agendar: (fn, ms) => { const id = ++proximo; timers.set(id, { fn, em: tempo + ms }); return id },
    cancelar: (id) => timers.delete(id), escutar: (nome, fn) => { ouvintes.set(nome, fn); return () => ouvintes.delete(nome) },
  }
  let estado = resposta().data, conectado = false, bloqueado = false, estados = 0
  const sync = criarSincronizacaoOperacao({ filialId: 1, token: 'sessao-de-teste', entregas, ambiente,
    consultar: (config) => { chamadas.push({ em: tempo, ...config }); return consultar ? consultar(config) : Promise.resolve(resposta()) },
    criarSocket: () => {
      const s = { pongs: true, fechado: false,
        send: () => { if (s.pongs) s.onmessage?.({ data: '{"evento":"pong"}' }) },
        close: () => { s.fechado = true },
        abrir: () => s.onopen(),
        receber: (msg) => s.onmessage?.({ data: JSON.stringify(msg) }),
        cair: (code = 1006) => s.onclose?.({ code }),
      }
      sockets.push(s); return s
    },
    onEstado: (dados) => { estado = dados; estados++ },
    onMensagem: (msg) => {
      estado = { ...estado, ...(msg.unidades ? { unidades: msg.unidades } : {}),
        ...(msg.alertas ? { alertas: msg.alertas } : {}), ...(msg.copeiras ? { copeiras: msg.copeiras } : {}),
        ...(msg.pedido ? { pedidos: atualizarPedidos(estado.pedidos, msg.pedido) } : {}) }
    },
    onConexao: (valor) => { conectado = valor }, onErro: (erro) => erros.push(erro),
    onBloqueio: (valor) => { bloqueado = valor; if (valor) estado = { ...estado, pedidos: [], copeiras: [] } },
    onCarregado: () => {},
  })
  async function avancar(ms) {
    const ate = tempo + ms
    while (true) {
      const tarefas = [...timers.entries()].filter(([, t]) => t.em <= ate).sort((a, b) => a[1].em - b[1].em)
      if (!tarefas.length) break
      const [id, tarefa] = tarefas[0]; timers.delete(id); tempo = tarefa.em
      tarefa.fn(); await flush()
    }
    tempo = ate; await flush()
  }
  return { sync, sockets, chamadas, erros, timers, ouvintes, avancar,
    get estado() { return estado }, get conectado() { return conectado }, get bloqueado() { return bloqueado }, get estados() { return estados },
    emitir: (nome) => ouvintes.get(nome)?.(), rede: (valor) => { rede = valor }, visivel: (valor) => { visivel = valor },
    iniciar: async () => { sync.iniciar(); sockets[0]?.abrir(); await flush() },
  }
}

test('24 horas estáveis: uma consulta inicial e 720 reconciliações, sem polling redundante', async () => {
  const t = montar(); await t.iniciar(); await t.avancar(86400000)
  assert.equal(t.chamadas.length, 721)
  assert.ok(t.chamadas.slice(1).every((c) => c.etag === '"v1"'))
  assert.equal(t.sockets.length, 1)
  assert.equal(t.conectado, true)
  t.sync.parar()
})

test('304 preserva o estado recebido pelo WebSocket', async () => {
  let n = 0
  const t = montar({ consultar: async () => ++n === 1 ? resposta() : { status: 304, headers: { etag: '"v1"' } } })
  await t.iniciar(); t.sockets[0].receber({ pedido: { id: 7, status: 'PRONTO' } })
  await t.avancar(120000)
  assert.equal(t.estados, 1)
  assert.equal(t.estado.pedidos[0].id, 7)
  t.sync.parar()
})

test('novo pedido, impressão, entrega e contexto chegam sem nova chamada HTTP', async () => {
  const t = montar(); await t.iniciar()
  t.sockets[0].receber({ pedido: { id: 7, status: 'PENDENTE' } })
  t.sockets[0].receber({ pedido: { id: 7, status: 'PRONTO', impressao: { estado: 'ENVIADO' } } })
  t.sockets[0].receber({ evento: 'contexto_atualizado', alertas: { preparo_minutos: 15 }, copeiras: [{ id: 4, nome: 'Fictícia' }] })
  assert.equal(t.estado.pedidos[0].impressao.estado, 'ENVIADO')
  assert.equal(t.estado.alertas.preparo_minutos, 15)
  assert.equal(t.estado.copeiras.length, 1)
  t.sockets[0].receber({ pedido: { id: 7, status: 'ENTREGUE' } })
  assert.deepEqual(t.estado.pedidos, [])
  assert.equal(t.chamadas.length, 1)
  t.sync.parar()
})

test('snapshot lento não ressuscita entrega nem apaga pedidos de outras atualizações', async () => {
  let concluir
  const t = montar({ consultar: () => new Promise((resolve) => { concluir = resolve }) })
  await t.iniciar()
  t.sockets[0].receber({ pedido: { id: 1, status: 'ENTREGUE' } })
  t.sockets[0].receber({ pedido: { id: 3, status: 'PRONTO' } })
  t.sockets[0].receber({ copeiras: [{ id: 4, nome: 'Fictícia' }] })
  concluir(resposta([{ id: 1, status: 'PRONTO' }, { id: 2, status: 'PENDENTE' }]))
  await flush()
  assert.deepEqual(t.estado.pedidos.map((p) => p.id), [2, 3])
  assert.equal(t.estado.copeiras.length, 1)
  t.sync.parar()
})

test('botão Atualizar e retomadas simultâneas compartilham uma consulta em andamento', async () => {
  let concluir
  const t = montar({ consultar: () => new Promise((resolve) => { concluir = resolve }) })
  await t.iniciar()
  const a = t.sync.recarregar(true), b = t.sync.recarregar(true)
  assert.equal(a, b); assert.equal(t.chamadas.length, 1)
  concluir(resposta()); await flush(); t.sync.parar()
})

test('WebSocket indisponível mantém consultas de Entregas a cada cinco segundos', async () => {
  const t = montar(); await t.iniciar(); t.sockets[0].cair()
  await t.avancar(15000)
  assert.ok(t.chamadas.length >= 4)
  assert.ok(t.chamadas.slice(1).every((c, i) => c.em - t.chamadas[i].em <= 5000))
  t.sync.parar()
})

test('API indisponível aumenta o intervalo de tentativas sem ser reiniciado pelos timeouts do socket', async () => {
  const t = montar({ consultar: async () => { throw { response: { status: 503 } } } })
  await t.iniciar(); t.sockets[0].cair(); await t.avancar(180000)
  assert.ok(t.chamadas.length <= 8, `Foram feitas ${t.chamadas.length} consultas`)
  assert.ok(t.erros.some(Boolean))
  t.sync.parar()
})

test('sem rede não há novas consultas e a volta reconcilia imediatamente', async () => {
  const t = montar(); await t.iniciar()
  t.rede(false); t.emitir('offline'); const antes = t.chamadas.length
  await t.avancar(180000)
  assert.equal(t.chamadas.length, antes)
  t.rede(true); t.emitir('online'); await flush()
  assert.equal(t.chamadas.length, antes + 1)
  t.sync.parar()
})

test('tela oculta mantém eventos mas suspende reconciliações até voltar ao primeiro plano', async () => {
  const t = montar(); await t.iniciar(); t.visivel(false)
  await t.avancar(600000)
  assert.equal(t.chamadas.length, 1)
  t.sockets[0].receber({ pedido: { id: 9, status: 'PRONTO' } })
  assert.equal(t.estado.pedidos[0].id, 9)
  t.visivel(true); t.emitir('visibilitychange'); await flush()
  assert.equal(t.chamadas.length, 2)
  t.sync.parar()
})

test('conexão silenciosamente interrompida é detectada pelo pulso e reabre o socket', async () => {
  const t = montar(); await t.iniciar(); t.sockets[0].pongs = false
  await t.avancar(80000)
  assert.equal(t.sockets[0].fechado, true)
  assert.ok(t.sockets.length >= 2)
  assert.ok(t.chamadas.length >= 2)
  t.sync.parar()
})

test('revogação fecha a conexão, limpa dados e interrompe tentativas automáticas', async () => {
  const t = montar(); await t.iniciar()
  t.sockets[0].receber({ pedido: { id: 3, status: 'PRONTO' }, copeiras: [{ id: 1, nome: 'Fictícia' }] })
  t.sockets[0].cair(1008)
  assert.equal(t.bloqueado, true)
  assert.deepEqual(t.estado.pedidos, []); assert.deepEqual(t.estado.copeiras, [])
  await t.avancar(600000)
  assert.equal(t.chamadas.length, 1)
  t.sync.parar()
})

test('resposta tardia de uma sessão desmontada não publica estado nem mantém ouvintes', async () => {
  let concluir
  const t = montar({ consultar: () => new Promise((resolve) => { concluir = resolve }) })
  await t.iniciar(); t.sync.parar()
  concluir(resposta([{ id: 99, status: 'PRONTO' }])); await flush()
  assert.equal(t.estados, 0)
  assert.equal(t.timers.size, 0); assert.equal(t.ouvintes.size, 0)
  assert.equal(t.chamadas[0].signal.aborted, true)
})

test('reconexão recupera mudanças ocorridas durante a desconexão', async () => {
  let n = 0
  const t = montar({ consultar: async () => resposta(++n > 1 ? [{ id: 8, status: 'PRONTO' }] : []) })
  await t.iniciar(); t.sockets[0].cair(); await t.avancar(1000)
  t.sockets[1].abrir(); await flush()
  assert.equal(t.conectado, true)
  assert.equal(t.estado.pedidos[0].id, 8)
  t.sync.parar()
})

test('HTTP que começou antes do WebSocket é seguido por conferência para fechar a janela sem eventos', async () => {
  let concluir, n = 0
  const t = montar({ consultar: async () => ++n === 1 ? new Promise((r) => { concluir = r }) : resposta([{ id: 5, status: 'PRONTO' }]) })
  t.sync.iniciar(); await t.avancar(1000); t.sockets[0].abrir()
  concluir(resposta()); await flush(); await t.avancar(0)
  assert.equal(t.chamadas.length, 2)
  assert.equal(t.estado.pedidos[0].id, 5)
  t.sync.parar()
})

test('Atualizar após bloqueio faz nova autorização sem reaproveitar ETag anterior', async () => {
  const t = montar(); await t.iniciar(); t.sockets[0].cair(1008)
  await t.sync.recarregar(true)
  assert.equal(t.chamadas.at(-1).etag, null)
  assert.equal(t.bloqueado, false)
  t.sync.parar()
})
