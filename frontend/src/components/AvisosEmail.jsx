import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { CAMPO, FiltroUnidade, Paginacao, PRIMARIO, SECUNDARIO } from './ConsultaGestao.jsx'
import { horarioBrasilia, mensagemErro } from '../services/painelOperacional.js'

const ESTADOS = { PENDENTE: 'Aguardando envio', PROCESSANDO: 'Enviando', ENVIADO: 'Aceito pelo servidor de e-mail',
  FALHA: 'Falha no envio', INCERTO: 'Precisa de conferência', CANCELADO: 'Cancelado', EXPIRADO: 'Prazo encerrado', DESATIVADO: 'Envio estava desativado' }

export default function AvisosEmail({ filiais }) {
  const [unidade, setUnidade] = useState(String(filiais[0]?.id || ''))
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ modo: 'GOOGLE_APP', remetente: '', habilitado: false, senha_app: '' })
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
      .then(({ data }) => { if (!controller.signal.aborted) { setConfig(data); setForm({ modo: data.modo, remetente: data.remetente, habilitado: data.habilitado, senha_app: '' }) } })
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

  function salvar(e) {
    e.preventDefault()
    executar(async () => {
      const { data } = await api.put(`/admin/avisos-email/${unidade}/configuracao`, {
        modo: form.modo, remetente: form.remetente.trim(), habilitado: form.habilitado,
        ...(form.modo === 'GOOGLE_APP' && form.senha_app.trim() ? { senha_app: form.senha_app } : {}),
      })
      setConfig(data); setForm((f) => ({ ...f, senha_app: '' })); setSucesso('Configuração de e-mail salva para esta unidade.')
    })
  }

  function reenviar(aviso, confirmar = false) {
    executar(async () => {
      const { data } = await api.post(`/admin/avisos-email/${unidade}/avisos/${aviso.id}/reenviar`, { confirmar_risco_duplicidade: confirmar })
      setSucesso(data.mensagem); setConferencia(null); setConferido(false); setAvisos(null); setRevisao((v) => v + 1)
    })
  }

  const mudou = config && (form.modo !== config.modo || form.remetente.trim() !== config.remetente || form.habilitado !== config.habilitado || Boolean(form.senha_app))

  return <section className="space-y-5" aria-labelledby="titulo-avisos-email">
    <div><p className="eyebrow">Um aviso para facilitar o recebimento</p><h2 id="titulo-avisos-email" className="mt-2 text-xl font-bold">E-mail das refeições médicas</h2>
      <p className="mt-2 text-sm text-slate-700">Quando a cozinha marcar uma refeição médica como Pronta, o solicitante receberá o aviso de saída com o resumo do pedido. Cada unidade utiliza seu próprio remetente.</p></div>
    {filiais.length ? <fieldset disabled={ocupado}><FiltroUnidade filiais={filiais} valor={unidade} todas={false} onChange={(v) => {
      setUnidade(v); setPagina(1); setErro(''); setSucesso(''); setConferencia(null); setConferido(false); setConfig(null); setAvisos(null)
      setForm({ modo: 'GOOGLE_APP', remetente: '', habilitado: false, senha_app: '' })
    }} /></fieldset>
      : <p className="rounded-xl bg-panel p-5">Cadastre uma unidade para configurar os avisos.</p>}
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
    {sucesso && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{sucesso}</p>}
    {unidade && !config && <p>Carregando configuração da unidade…</p>}
    {config && <form onSubmit={salvar} className="space-y-4 rounded-2xl bg-panel p-5">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block text-sm font-semibold">Forma de conexão<select className={`${CAMPO} mt-2`} value={form.modo} disabled={ocupado}
          onChange={(e) => setForm({ ...form, modo: e.target.value, senha_app: '' })}>
          <option value="GOOGLE_APP">Google Workspace · Senha de app</option><option value="GOOGLE_RELAY">Google Workspace · Relay autorizado pela TI</option></select></label>
        <label className="block text-sm font-semibold">E-mail da unidade / remetente<input className={`${CAMPO} mt-2`} type="email" required maxLength={254}
          autoComplete="off" placeholder="E-mail de dietas desta unidade" value={form.remetente} disabled={ocupado}
          onChange={(e) => setForm({ ...form, remetente: e.target.value, senha_app: '' })} /></label>
      </div>
      {form.modo === 'GOOGLE_APP' ? <>
        <p className="text-sm text-slate-700">O e-mail da unidade será usado como usuário. Gere uma senha de app na conta do Google, conforme a política da empresa. A conta precisa ter verificação em duas etapas e permissão para esse recurso.</p>
        {!config.protecao_preparada && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">A TI precisa preparar a proteção das credenciais no servidor antes de cadastrar a senha de app.</p>}
        {!config.acesso_seguro && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Para cadastrar a senha de app, abra o Cnutri por HTTPS ou nesta máquina em <a href="http://127.0.0.1:5173/admin" className="underline">http://127.0.0.1:5173/admin</a>.</p>}
        <label className="block text-sm font-semibold">Senha de app do Google<input className={`${CAMPO} mt-2`} type="password" maxLength={32} autoComplete="new-password"
          value={form.senha_app} disabled={ocupado || !config.protecao_preparada || !config.acesso_seguro} onChange={(e) => setForm({ ...form, senha_app: e.target.value })}
          placeholder={config.senha_configurada ? 'Já cadastrada · deixe vazio para manter' : '16 caracteres gerados pelo Google'} /></label>
        <p className="text-xs text-slate-700">A credencial é armazenada de forma criptografada e não é exibida após o cadastro.</p>
      </> : <p className="rounded-xl bg-brand-soft p-4 text-sm text-brand-ink">A TI deverá autorizar o IP de saída do servidor e os remetentes no relay do Google Workspace. Esta opção utiliza a conexão segura e dispensa cadastrar uma senha no Cnutri.</p>}
      <label className="flex items-start gap-3 text-sm font-semibold"><input type="checkbox" className="mt-1" checked={form.habilitado} disabled={ocupado}
        onChange={(e) => setForm({ ...form, habilitado: e.target.checked })} />Ativar os avisos desta unidade</label>
      <div className="flex flex-wrap gap-3"><button disabled={ocupado} className={PRIMARIO}>Salvar configuração</button>
        <button type="button" disabled={ocupado || mudou || !config.remetente} className={SECUNDARIO} onClick={() => executar(async () => {
          const { data } = await api.post(`/admin/avisos-email/${unidade}/testar`)
          setSucesso([data.mensagem, data.observacao].filter(Boolean).join('. '))
        })}>Testar conexão</button></div>
      <p className="text-xs text-slate-700">O teste verifica a conexão segura e a autenticação. Mensagens reais dependem também da autorização de envio do Google.</p>
    </form>}
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
