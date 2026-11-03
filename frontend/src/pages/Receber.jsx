import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { codigoRecebimentoValido, guardarCodigoRecebimento, nomeRecebedorValido, recebimentoApi, recuperarCodigoRecebimento } from '../services/recebimentoQr.js'
import { agoraBrasilia, dataEntregaISO, prepararFotoComprovante } from '../services/fotoComprovante.js'
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
  const [dataEntrega, setDataEntrega] = useState('')
  const [foto, setFoto] = useState(null)
  const [fotoUrl, setFotoUrl] = useState('')
  const [preparandoFoto, setPreparandoFoto] = useState(false)
  const [conferido, setConferido] = useState(false)
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)
  const [enviando, setEnviando] = useState(false)
  const enviandoRef = useRef(false)
  const selecaoFoto = useRef(0)
  const fotoUrlRef = useRef('')
  const valido = codigoRecebimentoValido(codigo)
  const autorizado = podeOperar(usuario, dados?.filial_id, ['NUTRICIONISTA', 'ADMIN_TI'])
  const precisaAcesso = dados && dados.status !== 'CANCELADO'
  const disponivel = autorizado && dados?.pode_confirmar && nomeRecebedorValido(recebedor) && dataEntregaISO(dataEntrega) && foto && conferido && !preparandoFoto

  useEffect(() => () => {
    selecaoFoto.current += 1
    if (fotoUrlRef.current) URL.revokeObjectURL(fotoUrlRef.current)
  }, [])

  function atualizarFoto(imagem) {
    if (fotoUrlRef.current) URL.revokeObjectURL(fotoUrlRef.current)
    fotoUrlRef.current = imagem ? URL.createObjectURL(imagem) : ''
    setFoto(imagem)
    setFotoUrl(fotoUrlRef.current)
  }

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
    if (!precisaAcesso || acessoCarregando) return
    if (!usuario || usuario.troca_senha_obrigatoria) {
      guardarCodigoRecebimento(codigo)
      navegar(usuario?.troca_senha_obrigatoria ? '/senha?retorno=%2Freceber' : LOGIN_QR, { replace: true })
    }
  }, [precisaAcesso, acessoCarregando, usuario, codigo, navegar])

  useEffect(() => {
    if (!autorizado) return
    const controller = new AbortController()
    api.post('/recebimentos/detalhes', { codigo }, { signal: controller.signal, timeout: 15000, ignorarRedirecionamento401: true })
      .then(({ data }) => { if (!controller.signal.aborted) setDados(data) })
      .catch(e => {
        if (controller.signal.aborted) return
        if (e.response?.status === 401) { guardarCodigoRecebimento(codigo); navegar(LOGIN_QR, { replace: true }); return }
        setErro(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Não foi possível consultar os dados da filipeta. Tente novamente.')
      })
    return () => controller.abort()
  }, [autorizado, codigo, usuario?.id, tentativa, navegar])

  async function confirmar(evento) {
    evento.preventDefault()
    if (enviandoRef.current || !disponivel) return
    enviandoRef.current = true
    setEnviando(true); setErro('')
    try {
      const formulario = new FormData()
      formulario.set('codigo', codigo)
      formulario.set('recebedor_nome', recebedor)
      formulario.set('entregue_em', dataEntregaISO(dataEntrega))
      formulario.set('foto', foto, 'filipeta.jpg')
      const { data } = await api.post('/recebimentos/confirmar', formulario, { timeout: 60000, ignorarRedirecionamento401: true })
      setDados(data)
      atualizarFoto(null); setConferido(false)
    } catch (e) {
      if (e.response?.status === 401) { guardarCodigoRecebimento(codigo); navegar(LOGIN_QR, { replace: true }); return }
      const detalhe = e.response?.data?.detail
      setErro(typeof detalhe === 'string' ? detalhe : 'Não foi possível confirmar. Tente novamente para conferir o mesmo recebimento.')
    } finally { enviandoRef.current = false; setEnviando(false) }
  }

  function consultarNovamente() { setErro(''); setTentativa((t) => t + 1) }

  async function selecionarFoto(evento) {
    const arquivo = evento.target.files?.[0]
    const selecao = ++selecaoFoto.current
    atualizarFoto(null); setConferido(false); setErro(''); setPreparandoFoto(false)
    if (!arquivo) return
    setPreparandoFoto(true)
    try {
      const preparada = await prepararFotoComprovante(arquivo)
      if (selecao === selecaoFoto.current) atualizarFoto(preparada)
    } catch (e) { if (selecao === selecaoFoto.current) setErro(e.message) }
    finally { if (selecao === selecaoFoto.current) setPreparandoFoto(false) }
  }

  function trocarConta() {
    void sair()
    guardarCodigoRecebimento(codigo)
    navegar(LOGIN_QR, { replace: true })
  }

  return <main className="auth-shell">
    <section className="receipt-card space-y-5">
      <header><MarcaAplicacao compacto /><h1 className="mt-5">Comprovar entrega</h1><p className="mt-3 text-sm text-slate-700">Nutrição: registre os dados da filipeta assinada e anexe a foto do comprovante.</p></header>
      {!valido ? <p role="alert">QR Code inválido. Escaneie o código da filipeta fornecida com a refeição.</p> : <>
        {dados && <div className="rounded-xl bg-brand-soft p-4"><p className="font-semibold">{dados.unidade}</p><p className="mt-1 text-sm">Pedido #{dados.pedido_id}</p></div>}
        {autorizado && dados?.destinatario && <div className="rounded-xl border border-slate-200 p-4 text-brand-ink"><p className="font-semibold">{dados.destinatario}</p><p className="mt-1 text-sm">{[dados.refeicao, dados.leito && `Leito ${dados.leito}`].filter(Boolean).join(' · ')}</p></div>}
        {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
        {!dados && !erro && <p role="status">Consultando refeição…</p>}
        {dados?.status === 'ENTREGUE' ? <div role="status" className="space-y-2 rounded-xl bg-emerald-50 p-4 text-emerald-950">
          <span className="inline-flex rounded-full bg-white p-2 text-emerald-800"><Icone nome="conferir" /></span>
          <h2 className="font-bold">Entrega registrada</h2>
          {dados.entregue_em && <p>Entrega: {horario(dados.entregue_em)}</p>}
          {autorizado && dados.recebedor_nome && <p>Recebedor: {dados.recebedor_nome}</p>}
          {dados.registrado_em && <p className="text-sm">Lançamento no sistema: {horario(dados.registrado_em)}</p>}
          <p className="text-sm">{dados.comprovante_disponivel ? 'A foto da filipeta está disponível no relatório de entregas da Nutrição.' : 'O comprovante anterior foi preservado.'}</p>
        </div> : dados?.status === 'CANCELADO' ? <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-950">Esta solicitação foi cancelada. Confira a refeição com a cozinha.</p>
          : precisaAcesso && (acessoCarregando || !usuario || usuario.troca_senha_obrigatoria) ? <p role="status">Abrindo o acesso da Nutrição neste dispositivo…</p>
            : precisaAcesso && !autorizado ? <p role="alert" className="rounded-xl bg-amber-50 p-4 text-amber-950">Entre com uma conta da Nutrição vinculada a esta unidade para registrar a entrega.</p>
                : dados?.pode_confirmar && autorizado ? <form onSubmit={confirmar} className="space-y-4">
            <label className="block text-sm font-semibold">Recebedor
              <input required autoComplete="name" autoCapitalize="words" minLength={3} maxLength={120} value={recebedor}
                onChange={(e) => setRecebedor(e.target.value)} disabled={enviando} placeholder="Nome completo de quem recebeu"
                className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal" />
            </label>
            <label className="block text-sm font-semibold">Data e hora da entrega (Brasília)
              <input required type="datetime-local" value={dataEntrega} max={agoraBrasilia()}
                onChange={(e) => setDataEntrega(e.target.value)} disabled={enviando}
                className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal" />
            </label>
            <p className="text-sm text-slate-700">Copie a data e a hora escritas no papel. O sistema registra separadamente quando você fez este lançamento.</p>
            <label className="block text-sm font-semibold">Foto da filipeta assinada
              <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={selecionarFoto} disabled={enviando || preparandoFoto}
                className="mt-2 block w-full min-w-0 rounded-lg border border-slate-300 bg-slate-50 p-3 text-sm font-normal" />
            </label>
            <p className="text-sm text-slate-700">Enquadre toda a filipeta, com boa luz. O nome, a assinatura, a data e a hora devem estar legíveis.</p>
            {preparandoFoto && <p role="status" className="text-sm">Preparando a foto…</p>}
            {fotoUrl && <div className="space-y-3"><a href={fotoUrl} target="_blank" rel="noreferrer" className="block"><img src={fotoUrl} alt="Prévia da filipeta assinada" className="max-h-96 w-full rounded-lg border border-slate-300 bg-white object-contain" /><span className="mt-2 block text-sm font-semibold text-brand underline">Ampliar foto para conferir</span></a>
              <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={conferido} onChange={e => setConferido(e.target.checked)} disabled={enviando} className="mt-1 h-5 w-5 shrink-0" />Conferi a foto: o pedido, o nome, a assinatura e a data e hora estão legíveis.</label></div>}
            <button type="submit" disabled={enviando || !disponivel} className={BOTAO}>{enviando ? 'Salvando comprovante…' : 'Registrar entrega e comprovante'}</button>
          </form> : dados && autorizado && <div className="space-y-3"><p>A refeição ainda não está pronta para recebimento.</p><button onClick={consultarNovamente} className={BOTAO}>Consultar novamente</button></div>}
        {erro && <button onClick={consultarNovamente} disabled={enviando} className="min-h-12 w-full rounded-lg bg-slate-50 px-4 py-3 font-semibold">Consultar novamente</button>}
        {usuario && <div className="border-t border-slate-200 pt-4 text-xs text-slate-700"><p>Acesso neste dispositivo: <strong>{usuario.nome}</strong></p>
          <button type="button" onClick={trocarConta} disabled={enviando} className="mt-2 font-semibold text-brand underline">Sair / trocar conta</button></div>}
      </>}
    </section>
  </main>
}
