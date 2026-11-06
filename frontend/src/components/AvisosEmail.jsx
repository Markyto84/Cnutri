import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { FiltroUnidade, Paginacao, PRIMARIO, SECUNDARIO } from './ConsultaGestao.jsx'
import { horarioBrasilia, mensagemErro } from '../services/painelOperacional.js'
import { configuracaoEmailAlterada, corpoConfiguracaoEmail, formularioEmail } from '../services/configuracaoEmail.js'
import FormConfiguracaoEmail from './FormConfiguracaoEmail.jsx'

const ESTADOS = { PENDENTE: 'Aguardando envio', PROCESSANDO: 'Enviando', ENVIADO: 'Aceito pelo servidor de e-mail',
  FALHA: 'Falha no envio', INCERTO: 'Precisa de conferência', CANCELADO: 'Cancelado', EXPIRADO: 'Prazo encerrado', DESATIVADO: 'Envio estava desativado' }

export default function AvisosEmail({ filiais }) {
  const [unidade, setUnidade] = useState(String(filiais[0]?.id || ''))
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState(() => formularioEmail())
  const [pagina, setPagina] = useState(1)
  const [avisos, setAvisos] = useState(null)
  const [revisao, setRevisao] = useState(0)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [conferencia, setConferencia] = useState(null)
  const [conferido, setConferido] = useState(false)

  useEffect(() => {
    if (!unidade) return
    const controller = new AbortController()
    api.get(`/admin/avisos-email/${unidade}/configuracao`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { setConfig(data); setForm(formularioEmail(data)) } })
      .catch((e) => { if (!controller.signal.aborted) setErro(mensagemErro(e)) })
    return () => controller.abort()
  }, [unidade])

  useEffect(() => {
    if (!unidade) return
    const controller = new AbortController()
    api.get(`/admin/avisos-email/${unidade}/avisos`, { params: { pagina }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setAvisos(data) })
      .catch((e) => { if (!controller.signal.aborted) setErro(mensagemErro(e)) })
    return () => controller.abort()
  }, [unidade, pagina, revisao])

  async function executar(acao) {
    setOcupado(true); setErro(''); setSucesso('')
    try { await acao() } catch (e) { setErro(mensagemErro(e)) } finally { setOcupado(false) }
  }

  function alterarConfiguracao(atualizacao) {
    setForm(atualizacao); setErro(''); setSucesso('')
  }

  function salvar(e) {
    e.preventDefault()
    executar(async () => {
      await gravarConfiguracao()
      setSucesso('Configuração de e-mail salva para esta unidade.')
    })
  }

  async function gravarConfiguracao() {
    const { data } = await api.put(`/admin/avisos-email/${unidade}/configuracao`, corpoConfiguracaoEmail(form))
    setConfig(data); setForm(formularioEmail(data))
  }

  function testar() {
    executar(async () => {
      if (mudou) await gravarConfiguracao()
      const { data } = await api.post(`/admin/avisos-email/${unidade}/testar`)
      const servidor = data.servidor_verificado
      setSucesso([data.mensagem, servidor && `Servidor verificado: ${servidor.servidor}:${servidor.porta}`, data.observacao].filter(Boolean).join(' '))
    })
  }

  function reenviar(aviso, confirmar = false) {
    executar(async () => {
      const { data } = await api.post(`/admin/avisos-email/${unidade}/avisos/${aviso.id}/reenviar`, { confirmar_risco_duplicidade: confirmar })
      setSucesso(data.mensagem); setConferencia(null); setConferido(false); setAvisos(null); setRevisao((v) => v + 1)
    })
  }

  const mudou = config && configuracaoEmailAlterada(form, config)

  return <section className="space-y-5" aria-labelledby="titulo-avisos-email">
    <div><p className="eyebrow">Um aviso para facilitar o recebimento</p><h2 id="titulo-avisos-email" className="mt-2 text-xl font-bold">E-mail das refeições médicas</h2>
      <p className="mt-2 text-sm text-slate-700">Quando a cozinha marcar uma refeição médica como Pronta, o solicitante receberá o aviso de saída com o resumo do pedido. Cada unidade utiliza seu próprio remetente.</p></div>
    {filiais.length ? <fieldset disabled={ocupado}><FiltroUnidade filiais={filiais} valor={unidade} todas={false} onChange={(v) => {
      setUnidade(v); setPagina(1); setErro(''); setSucesso(''); setConferencia(null); setConferido(false); setConfig(null); setAvisos(null)
      setForm(formularioEmail())
    }} /></fieldset>
      : <p className="rounded-xl bg-panel p-5">Cadastre uma unidade para configurar os avisos.</p>}
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
    {sucesso && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{sucesso}</p>}
    {unidade && !config && <p>Carregando configuração da unidade…</p>}
    {config && <FormConfiguracaoEmail config={config} form={form} setForm={alterarConfiguracao} ocupado={ocupado} mudou={mudou} salvar={salvar} testar={testar} />}
    {unidade && <section className="space-y-3 rounded-2xl bg-panel p-5" aria-labelledby="titulo-acompanhamento-email">
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 id="titulo-acompanhamento-email" className="font-bold">Acompanhamento dos avisos</h3>
        <button type="button" className={SECUNDARIO} disabled={ocupado} onClick={() => { setAvisos(null); setRevisao((v) => v + 1) }}>Atualizar avisos</button></div>
      <p className="text-sm text-slate-700">Um aviso aceito pelo servidor de e-mail ainda pode depender de filtros e da entrega na caixa de entrada. Avisos de saída podem ser enviados por até 30 minutos após a refeição ficar pronta.</p>
      {!avisos ? <p>Carregando avisos…</p> : <>
        {!avisos.total && <p className="text-sm">Ainda não há avisos registrados para esta unidade.</p>}
        {avisos.itens.map((aviso) => <article key={aviso.id} className="min-w-0 space-y-2 rounded-xl bg-white p-4">
          <div className="flex flex-wrap justify-between gap-2"><strong>Pedido #{aviso.pedido_id}</strong><span className="text-sm">{ESTADOS[aviso.estado] || aviso.estado}</span></div>
          <p className="break-all text-sm">{aviso.destinatario}</p><p className="text-xs text-slate-700">{horarioBrasilia(aviso.criado_em)} · {aviso.tentativas} tentativa(s){aviso.enviado_em && ` · Aceito em ${horarioBrasilia(aviso.enviado_em)}`}</p>
          {aviso.erro && <p className="text-sm text-amber-950">{aviso.erro}</p>}
          {['FALHA', 'DESATIVADO', 'INCERTO'].includes(aviso.estado) && <button className={SECUNDARIO} disabled={ocupado} onClick={() => {
            if (aviso.estado === 'INCERTO') { setConferencia(aviso); setConferido(false) } else reenviar(aviso)
          }}>{aviso.estado === 'INCERTO' ? 'Conferir antes de reenviar' : 'Tentar novamente'}</button>}
        </article>)}
        <Paginacao pagina={pagina} total={avisos.total} tamanho={20} onChange={(v) => { setAvisos(null); setPagina(v) }} />
      </>}
      {conferencia && <div className="space-y-3 rounded-xl border border-amber-300 bg-amber-50 p-4" role="region" aria-label="Conferência do reenvio">
        <p className="font-semibold">Conferir aviso do pedido #{conferencia.pedido_id}</p><p className="text-sm">O servidor pode ter recebido a mensagem antes da interrupção. Confirme com o destinatário para evitar um segundo aviso.</p>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={conferido} onChange={(e) => setConferido(e.target.checked)} />Conferi o recebimento e quero reenviar.</label>
        <div className="flex flex-wrap gap-3"><button className={PRIMARIO} disabled={ocupado || !conferido} onClick={() => reenviar(conferencia, true)}>Confirmar reenvio</button>
          <button className={SECUNDARIO} disabled={ocupado} onClick={() => setConferencia(null)}>Fechar</button></div>
      </div>}
    </section>}
  </section>
}
