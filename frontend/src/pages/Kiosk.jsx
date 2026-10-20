import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../services/api.js'
import FormDinamico from '../components/FormDinamico.jsx'

const REFEICOES = ['Almoço', 'Jantar', 'Ceia', 'Lanche']

export default function Kiosk({ slugPadrao }) {
  const { slug } = useParams()
  const slugFinal = slug || slugPadrao

  const [config, setConfig] = useState(null)
  const [erro, setErro] = useState(null)
  const [tela, setTela] = useState('perfil') // perfil | form | sucesso
  const [fluxo, setFluxo] = useState(null) // MEDICO | ENFERMAGEM
  const [enviando, setEnviando] = useState(false)
  const [erroEnvio, setErroEnvio] = useState(null)
  const [registro, setRegistro] = useState('') // CRM, COREN ou Matrícula — rastreabilidade obrigatória
  const [solicitanteNome, setSolicitanteNome] = useState('') // nome do profissional que solicita

  useEffect(() => {
    api
      .get(`/public/${slugFinal}/config`)
      .then((r) => setConfig(r.data))
      .catch((e) => setErro(e.response?.data?.detail || 'Erro ao contactar o servidor'))
  }, [slugFinal])

  if (erro)
    return (
      <div className="flex h-screen items-center justify-center bg-app-background text-slate-950 text-xl">
        {erro}
      </div>
    )
  if (!config)
    return <div className="flex h-screen items-center justify-center bg-app-background text-slate-950 text-xl">A carregar…</div>

  const dietaSelecionada = (id) => config.dietas.find((d) => d.id === Number(id))

  function traduzErro(e) {
    const detalhe = e.response?.data?.detail
    if (typeof detalhe === 'string') return detalhe
    if (Array.isArray(detalhe)) {
      const rotulos = {
        tipo_solicitacao: 'Tipo de solicitação',
        solicitante_identificacao: 'Registro profissional',
        nome_paciente: 'Nome do paciente',
      }
      return (
        'Campos com problema: ' +
        detalhe.map((d) => rotulos[d.loc?.[1]] || d.loc?.[1] || '?').join(', ')
      )
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
      await api.post(`/public/${slugFinal}/pedidos`, {
        ...dados,
        dados_dinamicos: dinamicos,
        solicitante_nome: solicitanteNome.trim(),
        solicitante_identificacao: registro.trim(),
        tipo_solicitacao: fluxo === 'MEDICO' ? 'MEDICO' : 'PACIENTE',
        dieta_id: dados.dieta_id ? Number(dados.dieta_id) : null,
      })
      setTela('sucesso')
    } catch (e) {
      setErroEnvio(traduzErro(e))
    } finally {
      setEnviando(false)
    }
  }

  if (tela === 'sucesso')
    return <Sucesso onVoltar={() => { setTela('perfil'); setFluxo(null) }} />

  return (
    <div className="min-h-screen bg-app-background text-slate-900 p-8">
      <header className="brand-header text-center mb-8">
        <h1 className="text-3xl font-bold text-brand">{config.filial.nome}</h1>
        <p className="text-slate-950 mt-1">Sistema de Gestão de Dietas</p>
      </header>

      {tela === 'perfil' && (
        <div className="mx-auto grid max-w-3xl grid-cols-1 gap-6 sm:grid-cols-2">
          <button
            onClick={() => { setFluxo('MEDICO'); setTela('form') }}
            className="rounded-2xl bg-brand p-10 text-2xl font-bold shadow-lg transition hover:scale-105 hover:bg-brand-hover text-white"
          >
            👨‍⚕️ Sou Médico
          </button>
          <button
            onClick={() => { setFluxo('ENFERMAGEM'); setTela('form') }}
            className="rounded-2xl bg-brand-vibrant p-10 text-2xl font-bold shadow-lg transition hover:scale-105 hover:bg-brand-vibrant-hover text-brand-ink"
          >
            🏥 Enfermagem / Paciente
          </button>
        </div>
      )}

      {tela === 'form' && (
        <div className="mx-auto max-w-2xl space-y-4">
          <div className="rounded-2xl bg-panel p-6 shadow-xl">
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Registro profissional (CRM, COREN ou Matrícula)<span className="text-red-700"> *</span>
            </label>
            <input
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              value={registro}
              onChange={(e) => setRegistro(e.target.value)}
              placeholder="Ex.: COREN-12345"
              autoFocus
            />
            <p className="mt-1 text-xs text-slate-700">Usado apenas para rastreabilidade e auditoria — sem necessidade de login.</p>
            <label className="mb-1 mt-4 block text-sm font-medium text-slate-700">
              Solicitante (seu nome)<span className="text-red-700"> *</span>
            </label>
            <input
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              value={solicitanteNome}
              onChange={(e) => setSolicitanteNome(e.target.value)}
              placeholder="Ex.: Enf. João Souza"
            />
          </div>
        <FormDinamico
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
        </div>
      )}
    </div>
  )
}

function Sucesso({ onVoltar }) {
  useEffect(() => {
    const t = setTimeout(onVoltar, 5000) // retorno automático em 5 segundos
    return () => clearTimeout(t)
  }, [onVoltar])

  return (
    <div className="flex h-screen flex-col items-center justify-center bg-app-background text-center">
      <div className="text-8xl">✅</div>
      <h2 className="mt-6 text-3xl font-bold text-slate-950">Pedido enviado com sucesso!</h2>
      <p className="mt-2 text-slate-950">A filipeta foi enviada à cozinha. Volta ao início em instantes…</p>
      <button onClick={onVoltar} className="mt-8 rounded-lg bg-slate-50 px-6 py-3 text-slate-800 hover:bg-slate-200">
        Voltar agora
      </button>
    </div>
  )
}
