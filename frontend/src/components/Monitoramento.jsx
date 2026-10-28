import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { estadoSondas, tamanhoLegivel, tempoAtivo } from '../services/monitoramento.js'
import { horarioBrasilia } from '../services/painelOperacional.js'
import { PRIMARIO, SECUNDARIO } from './ConsultaGestao.jsx'

const NOMES_BACKUP = { VALIDADO: 'Recuperação validada', EM_ANDAMENTO: 'Teste em andamento', FALHOU: 'Último teste falhou', SEM_TESTE: 'Ainda não testado', INCONSISTENTE: 'Relatório indisponível' }

function Indicador({ titulo, valor, bom, detalhe }) {
  return <article className="min-w-0 space-y-2 rounded-xl bg-panel p-4">
    <h3 className="font-semibold text-slate-700">{titulo}</h3>
    <p className={`break-words text-lg font-bold ${bom === true ? 'text-emerald-800' : bom === false ? 'text-red-800' : 'text-amber-900'}`}>{valor}</p>
    {detalhe && <p className="text-sm text-slate-700">{detalhe}</p>}
  </article>
}

export default function Monitoramento({ onAbrirCentral }) {
  const [dados, setDados] = useState(null)
  const [sondas, setSondas] = useState(null)
  const [atualizado, setAtualizado] = useState(null)
  const [erro, setErro] = useState('')
  const [revisao, setRevisao] = useState(0)
  const [carregando, setCarregando] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    let emCurso = false
    async function carregar() {
      if (emCurso) return
      emCurso = true
      try {
        const config = { signal: controller.signal, timeout: 5000 }
        const [saude, prontidao, monitor] = await Promise.allSettled([
          api.get('/health', config), api.get('/health/ready', config), api.get('/admin/monitoramento', config),
        ])
        if (controller.signal.aborted) return
        setSondas(estadoSondas(saude, prontidao))
        setDados(monitor.status === 'fulfilled' ? monitor.value.data : null)
        setErro(monitor.status === 'rejected' ? 'Não foi possível atualizar o monitoramento detalhado. Confira a conexão com o servidor e o banco.' : '')
        setAtualizado(new Date().toISOString())
      } finally { emCurso = false; if (!controller.signal.aborted) setCarregando(false) }
    }
    const inicial = setTimeout(carregar, 0)
    const timer = setInterval(carregar, 15000)
    return () => { controller.abort(); clearTimeout(inicial); clearInterval(timer) }
  }, [revisao])

  const banco = dados?.banco?.estado || sondas?.banco
  const apiEstado = sondas?.api
  const fila = dados?.fila
  const consumidor = dados?.consumidor
  const recuperacao = dados?.recuperacao
  const validacao = recuperacao?.ultima_validacao
  return <section className="min-w-0 space-y-4" aria-label="Monitoramento da aplicação">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-bold">Monitoramento do Cnutri</h2>
      <p className="mt-1 text-sm text-slate-700">API, banco, impressão e recuperação de backups · atualização a cada 15 segundos.</p>
      {atualizado && <p className="mt-1 text-xs text-slate-700">Última consulta: {horarioBrasilia(atualizado)}</p>}</div>
      <button className={SECUNDARIO} onClick={() => setRevisao((v) => v + 1)}>Atualizar monitoramento</button></div>
    {carregando && <p role="status">Consultando a aplicação…</p>}
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{erro}</p>}
    {dados?.banco?.consultas_operacionais === 'INDISPONIVEIS' && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-950">O banco respondeu à conexão, mas a consulta da fila não foi concluída.</p>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Indicador titulo="API" valor={!sondas ? 'Consultando…' : apiEstado === 'RESPONDENDO' ? 'Respondendo' : 'Sem resposta'} bom={sondas ? apiEstado === 'RESPONDENDO' : null}
        detalhe={dados && `Tempo ativo: ${tempoAtivo(dados.api.tempo_ativo_segundos)}`} />
      <Indicador titulo="Banco de dados" valor={!banco ? 'Consultando…' : banco === 'CONECTADO' ? 'Conectado' : banco === 'INDISPONIVEL' ? 'Indisponível' : 'Não foi possível verificar'}
        bom={banco ? banco === 'CONECTADO' : null} detalhe={dados?.banco?.latencia_ms != null ? `Resposta: ${dados.banco.latencia_ms} ms · Tamanho: ${tamanhoLegivel(dados.banco.tamanho_bytes)}` : ''} />
      <Indicador titulo="Processamento da impressão" valor={consumidor?.estado === 'ATIVA' ? 'Ativo' : consumidor?.estado === 'PARADA' ? 'Parado' : consumidor ? 'Precisa de atenção' : 'Não foi possível verificar'}
        bom={consumidor ? consumidor.estado === 'ATIVA' : null} detalhe={consumidor?.ultimo_sucesso_em ? `Último ciclo confirmado: ${horarioBrasilia(consumidor.ultimo_sucesso_em)}` : ''} />
      <Indicador titulo="Recuperação de backup" valor={recuperacao ? NOMES_BACKUP[recuperacao.estado] || 'Não informado' : 'Não foi possível verificar'}
        bom={recuperacao?.estado === 'VALIDADO' ? true : recuperacao?.estado === 'FALHOU' ? false : null}
        detalhe={validacao && `Última validação: ${horarioBrasilia(validacao.concluido_em)}`} />
    </div>
    <section className="space-y-4 rounded-xl bg-panel p-4 sm:p-6" aria-label="Situação da fila de impressão">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-bold">Fila de impressão</h3>
        <button className={PRIMARIO} onClick={onAbrirCentral}>Abrir central de impressões</button></div>
      {fila ? <>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[
          ['Pendentes', fila.contadores_24h.PENDENTE], ['Processando', fila.contadores_24h.PROCESSANDO],
          ['Falhas atuais', fila.falhas_atuais], ['Envios incertos atuais', fila.incertos_atuais],
        ].map(([nome, total]) => <div key={nome} className="min-w-0 rounded-lg bg-white p-3"><p className="text-sm text-slate-700">{nome}</p><p className="mt-1 text-2xl font-bold">{total}</p></div>)}</div>
        <p className="text-sm text-slate-700">Trabalhos criados nas últimas 24h: {fila.contadores_24h.ENVIADO} enviado(s), {fila.contadores_24h.FALHA} falha(s), {fila.contadores_24h.INCERTO} envio(s) incerto(s). Pendências incluem qualquer data.</p>
        {fila.pendente_mais_antigo_em && <p className="text-sm">Mais antigo na fila: {horarioBrasilia(fila.pendente_mais_antigo_em)}</p>}
        {fila.processando_mais_60s > 0 && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{fila.processando_mais_60s} trabalho(s) em processamento há mais de um minuto. Confira a central antes de reenviar.</p>}
        <p className="text-sm text-slate-700">A transmissão dos dados não confirma a saída física do papel.</p>
      </> : <p className="text-sm text-slate-700">Contadores da fila indisponíveis nesta consulta.</p>}
    </section>
    <section className="space-y-3 rounded-xl bg-panel p-4 sm:p-6" aria-label="Validação de recuperação">
      <h3 className="text-lg font-bold">Teste de recuperação</h3>
      {validacao ? <><p className="text-sm text-slate-700">Conferência em banco separado, sem iniciar impressão.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
          ['Tabelas verificadas', validacao.tabelas_verificadas], ['Registros conferidos', validacao.registros_verificados],
          ['Formulários', validacao.formularios_verificados], ['Assinaturas', validacao.assinaturas_verificadas],
        ].map(([nome, total]) => <p key={nome} className="rounded-lg bg-white p-3 text-sm"><span className="block text-slate-700">{nome}</span><strong className="text-xl">{total}</strong></p>)}</div>
        <p className="text-sm">Duração: {validacao.duracao_segundos} segundos · Ambiente temporário {validacao.temporario_removido ? 'removido após a conferência' : 'aguardando remoção'}.</p>
      </> : <p className="text-sm text-slate-700">Nenhuma recuperação validada foi registrada. A TI executa a ferramenta de validação no ambiente de manutenção.</p>}
      {recuperacao?.estado === 'FALHOU' && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">O último teste não foi concluído com sucesso. A data acima se refere à última validação bem-sucedida, quando houver.</p>}
      {recuperacao?.estado === 'EM_ANDAMENTO' && <p role="status" className="text-sm">Há um teste de recuperação em andamento.</p>}
    </section>
  </section>
}
