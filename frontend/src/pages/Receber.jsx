import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { codigoRecebimentoValido, guardarCodigoRecebimento, nomeRecebedorValido, recebimentoApi, recuperarCodigoRecebimento, registroRecebimentoValido } from '../services/recebimentoQr.js'
import { api } from '../services/api.js'
import { podeOperar, useAuth } from '../context/auth.js'
import { Icone, MarcaAplicacao } from '../components/Identidade.jsx'

const horario = (valor) => new Date(valor).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
const BOTAO = 'ui-button ui-button-primary min-h-12 w-full'
const LOGIN_QR = '/login?retorno=%2Freceber'

export default function Receber() {
  const { hash } = useLocation()
  const navegar = useNavigate()
  const codigo = hash ? hash.slice(1) : recuperarCodigoRecebimento()
  useEffect(() => {
    if (!hash && codigoRecebimentoValido(codigo)) navegar(`/receber#${codigo}`, { replace: true })
  }, [hash, codigo, navegar])
  return <ConfirmarRecebimento key={codigo} codigo={codigo} />
}

function ConfirmarRecebimento({ codigo }) {
  const navegar = useNavigate()
  const { usuario, carregando: acessoCarregando, sair } = useAuth()
  const [dados, setDados] = useState(null)
  const [recebedor, setRecebedor] = useState('')
  const [registro, setRegistro] = useState('')
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)
  const [enviando, setEnviando] = useState(false)
  const [identificadoPor, setIdentificadoPor] = useState(null)
  const enviandoRef = useRef(false)
  const valido = codigoRecebimentoValido(codigo)
  const autorizado = podeOperar(usuario, dados?.filial_id, ['COPEIRA'])
  const emAberto = dados && !['ENTREGUE', 'CANCELADO'].includes(dados.status)
  const identificado = identificadoPor != null && identificadoPor === usuario?.id

  useEffect(() => {
    if (!valido) return
    const controller = new AbortController()
    recebimentoApi.post('/consultar', { codigo }, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setDados(data) })
      .catch((e) => { if (!controller.signal.aborted) setErro(typeof e.response?.data?.detail === 'string'
        ? e.response.data.detail : 'Não foi possível consultar a refeição. Verifique a conexão e tente novamente.') })
    return () => controller.abort()
  }, [codigo, valido, tentativa])

  useEffect(() => {
    if (!emAberto || acessoCarregando) return
    if (!usuario || usuario.troca_senha_obrigatoria) {
      guardarCodigoRecebimento(codigo)
      navegar(usuario?.troca_senha_obrigatoria ? '/senha?retorno=%2Freceber' : LOGIN_QR, { replace: true })
    }
  }, [emAberto, acessoCarregando, usuario, codigo, navegar])

  useEffect(() => {
    if (!autorizado || dados?.status !== 'PRONTO' || identificado) return
    const controller = new AbortController()
    api.post('/recebimentos/identificar', { codigo }, { signal: controller.signal, timeout: 15000, ignorarRedirecionamento401: true })
      .then(({ data }) => { if (!controller.signal.aborted) { setDados(data); setIdentificadoPor(usuario.id) } })
      .catch(e => {
        if (controller.signal.aborted) return
        if (e.response?.status === 401) { guardarCodigoRecebimento(codigo); navegar(LOGIN_QR, { replace: true }); return }
        setErro(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Não foi possível identificar a copeira. Consulte novamente.')
      })
    return () => controller.abort()
  }, [autorizado, dados?.status, identificado, codigo, usuario?.id, tentativa, navegar])

  useEffect(() => {
    if (!autorizado || dados?.status !== 'PRONTO') return
    const controller = new AbortController()
    async function presenca() {
      try { await api.post('/auth/presenca', { filial_id: dados.filial_id }, { signal: controller.signal, timeout: 15000, ignorarRedirecionamento401: true }) }
      catch (e) { if (!controller.signal.aborted && e.response?.status === 401) { guardarCodigoRecebimento(codigo); navegar(LOGIN_QR, { replace: true }) } }
    }
    void presenca()
    const intervalo = setInterval(presenca, 30000)
    return () => { controller.abort(); clearInterval(intervalo) }
  }, [autorizado, dados?.filial_id, dados?.status, codigo, navegar])

  async function confirmar(evento) {
    evento.preventDefault()
    if (enviandoRef.current || !identificado || !autorizado || !dados?.pode_confirmar || !nomeRecebedorValido(recebedor) || !registroRecebimentoValido(registro)) return
    enviandoRef.current = true
    setEnviando(true); setErro('')
    try {
      const { data } = await api.post('/recebimentos/confirmar', { codigo, recebedor_nome: recebedor, registro_profissional: registro }, { timeout: 15000, ignorarRedirecionamento401: true })
      setDados(data)
    } catch (e) {
      if (e.response?.status === 401) { guardarCodigoRecebimento(codigo); navegar(LOGIN_QR, { replace: true }); return }
      const detalhe = e.response?.data?.detail
      setErro(typeof detalhe === 'string' ? detalhe : 'Não foi possível confirmar. Tente novamente para conferir o mesmo recebimento.')
    } finally { enviandoRef.current = false; setEnviando(false) }
  }

  function consultarNovamente() { setErro(''); setDados(null); setIdentificadoPor(null); setTentativa((t) => t + 1) }

  function trocarConta() {
    void sair()
    guardarCodigoRecebimento(codigo)
    navegar(LOGIN_QR, { replace: true })
  }

  return <main className="auth-shell">
    <section className="receipt-card space-y-5">
      <header><MarcaAplicacao compacto /><h1 className="mt-5">Recebimento da refeição</h1><p className="mt-3 text-sm text-slate-700">Sua confirmação completa esta etapa do cuidado.</p></header>
      {!valido ? <p role="alert">QR Code inválido. Escaneie o código da filipeta fornecida com a refeição.</p> : <>
        {dados && <div className="rounded-xl bg-brand-soft p-4"><p className="font-semibold">{dados.unidade}</p><p className="mt-1 text-sm">Pedido #{dados.pedido_id}</p></div>}
        {dados?.copeira_nome && <div className="flex items-start gap-3 rounded-xl border border-slate-200 p-4 text-brand-ink"><Icone nome="entrega" />
          <div><p className="text-xs text-slate-700">Copeira responsável pela entrega</p><p className="mt-1 font-semibold">{dados.copeira_nome}</p>
            {dados.retirada_em && <p className="mt-1 text-xs text-slate-700">Identificação: {horario(dados.retirada_em)}</p>}</div></div>}
        {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
        {!dados && !erro && <p role="status">Consultando refeição…</p>}
        {dados?.status === 'ENTREGUE' ? <div role="status" className="space-y-2 rounded-xl bg-emerald-50 p-4 text-emerald-950">
          <span className="inline-flex rounded-full bg-white p-2 text-emerald-800"><Icone nome="conferir" /></span>
          <h2 className="font-bold">Recebimento confirmado</h2>
          {dados.confirmado_em && <p>Data e hora: {horario(dados.confirmado_em)}</p>}
          <p className="text-sm">Obrigado. A entrega está registrada e você já pode fechar esta página.</p>
        </div> : dados?.status === 'CANCELADO' ? <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-950">Esta solicitação foi cancelada. Confira a refeição com a cozinha.</p>
          : emAberto && (acessoCarregando || !usuario || usuario.troca_senha_obrigatoria) ? <p role="status">Abrindo o acesso da copeira neste dispositivo…</p>
            : emAberto && !autorizado ? <p role="alert" className="rounded-xl bg-amber-50 p-4 text-amber-950">Entre com uma conta de copeira vinculada a esta unidade para identificar a entrega.</p>
              : dados?.status === 'PRONTO' && !identificado ? !erro && <p role="status">Identificando a copeira responsável pela entrega…</p>
                : dados?.pode_confirmar && identificado && autorizado ? <form onSubmit={confirmar} className="space-y-4">
            <label className="block text-sm font-semibold">Recebedor
              <input required autoComplete="name" autoCapitalize="words" minLength={3} maxLength={120} value={recebedor}
                onChange={(e) => setRecebedor(e.target.value)} disabled={enviando} placeholder="Nome completo de quem recebeu"
                className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal" />
            </label>
            <label className="block text-sm font-semibold">Registro profissional do recebedor
              <input required autoComplete="off" autoCapitalize="characters" minLength={3} maxLength={50} value={registro}
                onChange={(e) => setRegistro(e.target.value)} disabled={enviando} placeholder="Ex.: COREN-SP 123456"
                className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal" />
            </label>
            <p className="text-sm text-slate-700">Informe o nome e o registro profissional de quem recebeu a refeição e confirme o recebimento.</p>
            <button type="submit" disabled={enviando || !nomeRecebedorValido(recebedor) || !registroRecebimentoValido(registro)} className={BOTAO}>{enviando ? 'Confirmando…' : 'Confirmar recebimento'}</button>
          </form> : dados && autorizado && <div className="space-y-3"><p>A refeição ainda não está pronta para recebimento.</p><button onClick={consultarNovamente} className={BOTAO}>Consultar novamente</button></div>}
        {erro && <button onClick={consultarNovamente} disabled={enviando} className="min-h-12 w-full rounded-lg bg-slate-50 px-4 py-3 font-semibold">Consultar novamente</button>}
        {emAberto && usuario && <div className="border-t border-slate-200 pt-4 text-xs text-slate-700"><p>Acesso neste dispositivo: <strong>{usuario.nome}</strong></p>
          <button type="button" onClick={trocarConta} disabled={enviando} className="mt-2 font-semibold text-brand underline">Sair / trocar conta da copeira</button></div>}
      </>}
    </section>
  </main>
}
