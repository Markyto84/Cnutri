import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { kioskApi } from '../services/kioskApi.js'
import FormDinamico from '../components/FormDinamico.jsx'
import NaoEncontrado from './NaoEncontrado.jsx'
import { chaveSalva, concluirTentativa, obterChaveEnvio, textoImpressao } from '../services/solicitacoes.js'
import { Icone, IlustracaoCuidado, MarcaAplicacao } from '../components/Identidade.jsx'

export default function Kiosk() {
  const { slug: slugFinal } = useParams()

  const [config, setConfig] = useState(null)
  const [erro, setErro] = useState(null)
  const [tentativa, setTentativa] = useState(0)
  const [tela, setTela] = useState('perfil') // perfil | form | sucesso
  const [fluxo, setFluxo] = useState(null) // MEDICO | ENFERMAGEM
  const [enviando, setEnviando] = useState(false)
  const [erroEnvio, setErroEnvio] = useState(null)
  const [resultado, setResultado] = useState(null)
  const [registro, setRegistro] = useState('') // CRM, COREN ou Matrícula — rastreabilidade obrigatória
  const [solicitanteNome, setSolicitanteNome] = useState('') // nome do profissional que solicita

  useEffect(() => {
    const controller = new AbortController()
    kioskApi
      .get(`/${slugFinal}/config`, { signal: controller.signal })
      .then((r) => { if (!controller.signal.aborted) setConfig(r.data) })
      .catch((e) => { if (!controller.signal.aborted) setErro({ status: e.response?.status,
        mensagem: typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Não foi possível carregar o formulário. Verifique a conexão e tente novamente.' }) })
    const chave = chaveSalva(slugFinal)
    if (chave) kioskApi.get(`/${slugFinal}/solicitacoes/${chave}`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { setResultado(data); setTela('sucesso') } })
      .catch(() => { /* mantém a chave para repetir o envio após uma falha de rede */ })
    return () => controller.abort()
  }, [slugFinal, tentativa])

  if (erro?.status === 404) return <NaoEncontrado />
  if (erro)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-app-background p-6 text-center text-slate-950">
        <p role="alert">{erro.mensagem}</p>
        <button onClick={() => { setErro(null); setConfig(null); setTentativa((t) => t + 1) }} className="rounded-lg bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-hover">Tentar novamente</button>
      </div>
    )
  if (!config)
    return <div role="status" className="auth-shell"><div className="space-y-5 text-center"><MarcaAplicacao /><p>Preparando o formulário da sua unidade…</p></div></div>

  const dietaSelecionada = (id) => config.dietas.find((d) => d.id === Number(id))

  function traduzErro(e) {
    const detalhe = e.response?.data?.detail
    if (typeof detalhe === 'string') return detalhe
    if (Array.isArray(detalhe)) {
      return detalhe.map((d) => {
        if (d.type === 'value_error') return d.msg.replace(/^Value error, /, '')
        const chave = d.loc?.at(-1)
        const rotulo = config.formularios?.[fluxo]?.campos?.find((c) => c.id === chave)?.rotulo
          || ({ solicitante_nome: 'Solicitante', solicitante_identificacao: 'Registro profissional' })[chave] || 'Formulário'
        const mensagem = ({ string_too_short: 'preenchimento obrigatório', missing: 'preenchimento obrigatório',
          string_too_long: 'texto maior que o limite permitido' })[d.type] || 'informe um valor válido'
        return `${rotulo}: ${mensagem}`
      }).join('. ')
    }
    return 'Verifique os campos obrigatórios'
  }

  async function enviar(dados) {
    if (!registro.trim()) {
      setErroEnvio('Informe o seu registro profissional (CRM, COREN ou Matrícula)')
      return
    }
    if (!solicitanteNome.trim()) {
      setErroEnvio('Informe o seu nome no campo Solicitante')
      return
    }
    // Campos "conhecidos" pelo backend; todo o restante vai em dados_dinamicos (JSONB)
    const fixos = ['leito', 'prontuario', 'nome_paciente', 'dieta_id', 'observacoes_alergias', 'solicitante_nome']
    const dinamicos = Object.fromEntries(Object.entries(dados).filter(([k]) => !fixos.includes(k)))

    setEnviando(true)
    setErroEnvio(null)
    try {
      const resposta = await kioskApi.post(`/${slugFinal}/pedidos`, {
        ...Object.fromEntries(Object.entries(dados).filter(([k]) => fixos.includes(k))),
        dados_dinamicos: dinamicos,
        solicitante_nome: solicitanteNome.trim(),
        solicitante_identificacao: registro.trim(),
        tipo_solicitacao: fluxo === 'MEDICO' ? 'MEDICO' : 'PACIENTE',
        dieta_id: dados.dieta_id ? Number(dados.dieta_id) : null,
      }, { headers: { 'Idempotency-Key': obterChaveEnvio(slugFinal) } })
      setResultado(resposta.data)
      setTela('sucesso')
    } catch (e) {
      const anterior = e.response?.data?.detail
      if (e.response?.status === 409 && anterior?.pedido_id) {
        setResultado({ id: anterior.pedido_id, impressao: anterior.impressao, aviso: anterior.mensagem })
        setTela('sucesso')
      } else setErroEnvio(e.response ? traduzErro(e) : 'A conexão foi interrompida. Tente enviar novamente para consultar e confirmar a mesma solicitação.')
    } finally {
      setEnviando(false)
    }
  }

  if (tela === 'sucesso')
    return <Sucesso resultado={resultado} slug={slugFinal} onVoltar={() => { concluirTentativa(slugFinal); setResultado(null); setTela('perfil'); setFluxo(null); setRegistro(''); setSolicitanteNome('') }} />

  return (
    <div className="app-shell kiosk-shell">
      <header className="kiosk-topbar">
        <MarcaAplicacao />
        <p className="unit-pill"><Icone nome="unidade" tamanho={20} /><span>{config.filial.nome}</span></p>
      </header>

      {tela === 'perfil' && (
        <main className="kiosk-content">
          <section className="care-intro">
            <div><p className="eyebrow">Bem-vindo ao Cnutri</p>
              <h1>Uma refeição,<br /><span>muitos cuidados.</span></h1>
              <p>Escolha o tipo de solicitação para começar. Sua equipe de nutrição acompanha os próximos passos.</p>
            </div>
            <IlustracaoCuidado />
          </section>
        <div className="profile-grid" aria-label="Tipo de solicitação">
          <button
            onClick={() => { setFluxo('MEDICO'); setTela('form') }}
            className="profile-card"
          >
            <span className="profile-card-icon"><Icone nome="profissional" tamanho={28} /></span>
            <span className="profile-card-arrow"><Icone nome="seta" tamanho={20} /></span>
            <span className="profile-card-title">Médico / Administração</span>
            <span className="profile-card-description">Solicite a refeição da sua equipe, com os detalhes de entrega.</span>
          </button>
          <button
            onClick={() => { setFluxo('ENFERMAGEM'); setTela('form') }}
            className="profile-card profile-card-patient"
          >
            <span className="profile-card-icon"><Icone nome="cuidado" tamanho={28} /></span>
            <span className="profile-card-arrow"><Icone nome="seta" tamanho={20} /></span>
            <span className="profile-card-title">Enfermagem / Paciente</span>
            <span className="profile-card-description">Solicite a dieta do paciente e, quando necessário, do acompanhante.</span>
          </button>
        </div>
          <ol className="journey-strip" aria-label="Etapas da solicitação">
            {[['1', 'Solicitação', 'Preencha os dados da refeição.'], ['2', 'Preparo', 'A cozinha recebe sua solicitação.'], ['3', 'Recebimento', 'Confirme a entrega pelo QR Code.']].map(([numero, titulo, texto]) =>
              <li key={numero} className="journey-step"><span>{numero}</span><div><strong>{titulo}</strong><p>{texto}</p></div></li>)}
          </ol>
          <p className="care-footer">Cuidado em cada etapa, da solicitação à entrega.</p>
        </main>
      )}

      {tela === 'form' && (
        <main className="form-content space-y-5">
          <button type="button" onClick={() => setTela('perfil')} className="ui-button ui-button-secondary"><Icone nome="voltar" tamanho={18} />Voltar às solicitações</button>
          <div className="form-intro"><p className="eyebrow">{fluxo === 'MEDICO' ? 'Médico / Administração' : 'Enfermagem / Paciente'}</p>
            <h1>Vamos cuidar desta solicitação.</h1><p>Informe os dados abaixo. Os campos com <span className="text-red-700">*</span> são obrigatórios.</p></div>
          <section aria-labelledby="titulo-solicitante" className="form-card rounded-2xl bg-panel p-5 sm:p-7">
            <div className="form-card-heading"><span className="form-step">1</span><div><h2 id="titulo-solicitante">Quem está solicitando?</h2><p>Sua identificação acompanha a solicitação.</p></div></div>
            <label htmlFor="registro-solicitante" className="mb-2 block text-sm font-semibold text-slate-700">
              Registro profissional (CRM, COREN ou Matrícula)<span className="text-red-700"> *</span>
            </label>
            <input
              id="registro-solicitante"
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              maxLength={50}
              value={registro}
              onChange={(e) => setRegistro(e.target.value)}
              placeholder="Ex.: COREN-12345"
              autoFocus
            />
            <p className="mt-2 text-xs text-slate-700">Informe CRM, COREN ou matrícula profissional. Não é necessário entrar em uma conta.</p>
            <label htmlFor="nome-solicitante" className="mb-2 mt-5 block text-sm font-semibold text-slate-700">
              Solicitante (seu nome)<span className="text-red-700"> *</span>
            </label>
            <input
              id="nome-solicitante"
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              maxLength={100}
              value={solicitanteNome}
              onChange={(e) => setSolicitanteNome(e.target.value)}
              placeholder="Ex.: Enf. João Souza"
            />
          </section>
        <FormDinamico
          etapa="2"
          titulo={config.formularios?.[fluxo]?.titulo || (fluxo === 'MEDICO' ? 'Solicitação — Profissional' : 'Solicitação — Paciente')}
          cabecalho={config.formularios?.[fluxo]?.cabecalho || ''}
          destacarCabecalho={fluxo === 'MEDICO'}
          campos={config.formularios?.[fluxo]?.campos || []}
          dietas={config.dietas}
          dietaSelecionada={dietaSelecionada}
          enviando={enviando}
          erro={erroEnvio}
          onCancelar={() => setTela('perfil')}
          onEnviar={enviar}
        />
        </main>
      )}
    </div>
  )
}

function Sucesso({ resultado, slug, onVoltar }) {
  const [impressao, setImpressao] = useState(resultado.impressao)
  useEffect(() => {
    const t = setTimeout(onVoltar, 20000)
    return () => clearTimeout(t)
  }, [onVoltar])
  useEffect(() => {
    const chave = chaveSalva(slug)
    if (!chave) return
    const controller = new AbortController()
    const intervalo = setInterval(() => kioskApi.get(`/${slug}/solicitacoes/${chave}`, { signal: controller.signal })
      .then(({ data }) => setImpressao(data.impressao)).catch(() => {}), 2000)
    return () => { clearInterval(intervalo); controller.abort() }
  }, [slug])

  return (
    <div className="auth-shell text-center"><section className="receipt-card flex flex-col items-center">
      <div className="success-halo"><Icone nome="conferir" tamanho={32} /></div>
      <h2 className="mt-6 text-3xl font-bold text-slate-950">Pedido #{resultado.id} registrado</h2>
      <p className="mt-3 text-slate-700">Sua solicitação foi recebida. Obrigado por cuidar de cada detalhe.</p>
      <p className="mt-4 font-semibold text-brand" role="status">{textoImpressao(impressao?.estado)}</p>
      {impressao?.erro && <p className="mt-2 max-w-xl text-sm text-red-800">{impressao.erro}</p>}
      {['FALHA', 'INCERTO'].includes(impressao?.estado) && <p className="mt-2 text-sm text-slate-800">Informe o número do pedido à cozinha para conferir ou reenviar a filipeta.</p>}
      {resultado.aviso && <p className="mt-4 max-w-xl rounded-lg bg-amber-50 p-4 text-sm text-amber-950">{resultado.aviso}</p>}
      <p className="mt-5 text-sm text-slate-700">Guarde o número do pedido. Retorno ao início em 20 segundos.</p>
      <button onClick={onVoltar} className="ui-button ui-button-primary mt-8 w-full">
        Nova solicitação
      </button>
    </section></div>
  )
}
