import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { codigoRecebimentoValido, recebimentoApi, registroRecebimentoValido } from '../services/recebimentoQr.js'

const horario = (valor) => new Date(valor).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })
const BOTAO = 'min-h-12 w-full rounded-xl bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50'

export default function Receber() {
  const { hash } = useLocation()
  return <ConfirmarRecebimento key={hash} codigo={hash.slice(1)} />
}

function ConfirmarRecebimento({ codigo }) {
  const [dados, setDados] = useState(null)
  const [registro, setRegistro] = useState('')
  const [erro, setErro] = useState('')
  const [tentativa, setTentativa] = useState(0)
  const [enviando, setEnviando] = useState(false)
  const enviandoRef = useRef(false)
  const valido = codigoRecebimentoValido(codigo)

  useEffect(() => {
    if (!valido) return
    const controller = new AbortController()
    recebimentoApi.post('/consultar', { codigo }, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setDados(data) })
      .catch((e) => { if (!controller.signal.aborted) setErro(typeof e.response?.data?.detail === 'string'
        ? e.response.data.detail : 'Não foi possível consultar a refeição. Verifique a conexão e tente novamente.') })
    return () => controller.abort()
  }, [codigo, valido, tentativa])

  async function confirmar(evento) {
    evento.preventDefault()
    if (enviandoRef.current || !dados?.pode_confirmar || !registroRecebimentoValido(registro)) return
    enviandoRef.current = true
    setEnviando(true); setErro('')
    try {
      const { data } = await recebimentoApi.post('/confirmar', { codigo, registro_profissional: registro })
      setDados(data)
    } catch (e) {
      const detalhe = e.response?.data?.detail
      setErro(typeof detalhe === 'string' ? detalhe : 'Não foi possível confirmar. Tente novamente para conferir o mesmo recebimento.')
    } finally { enviandoRef.current = false; setEnviando(false) }
  }

  function consultarNovamente() { setErro(''); setDados(null); setTentativa((t) => t + 1) }

  return <main className="flex min-h-screen items-center justify-center bg-app-background p-4 text-slate-900">
    <section className="w-full max-w-md space-y-5 rounded-2xl border-t-4 border-brand-vibrant bg-panel p-5 shadow-sm sm:p-8">
      <header><p className="text-sm font-semibold text-brand">Cnutri</p><h1 className="mt-2 text-2xl font-bold">Recebimento da refeição</h1></header>
      {!valido ? <p role="alert">QR Code inválido. Escaneie o código da filipeta fornecida com a refeição.</p> : <>
        {dados && <div className="rounded-xl bg-brand-soft p-4"><p className="font-semibold">{dados.unidade}</p><p className="mt-1 text-sm">Pedido #{dados.pedido_id}</p></div>}
        {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
        {!dados && !erro && <p role="status">Consultando refeição…</p>}
        {dados?.status === 'ENTREGUE' ? <div role="status" className="space-y-2 rounded-xl bg-emerald-50 p-4 text-emerald-950">
          <h2 className="font-bold">Recebimento já confirmado</h2>
          {dados.confirmado_em && <p>Data e hora: {horario(dados.confirmado_em)}</p>}
          <p className="text-sm">A entrega está registrada. Você pode fechar esta página.</p>
        </div> : dados?.status === 'CANCELADO' ? <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-950">Esta solicitação foi cancelada. Confira a refeição com a cozinha.</p>
          : dados?.pode_confirmar ? <form onSubmit={confirmar} className="space-y-4">
            <label className="block text-sm font-semibold">Registro profissional do recebedor
              <input required autoComplete="off" autoCapitalize="characters" minLength={3} maxLength={50} value={registro}
                onChange={(e) => setRegistro(e.target.value)} disabled={enviando} placeholder="Ex.: COREN-SP 123456"
                className="mt-2 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base font-normal" />
            </label>
            <p className="text-sm text-slate-700">Informe o registro profissional de quem recebeu a refeição e confirme o recebimento.</p>
            <button type="submit" disabled={enviando || !registroRecebimentoValido(registro)} className={BOTAO}>{enviando ? 'Confirmando…' : 'Confirmar recebimento'}</button>
          </form> : dados && <div className="space-y-3"><p>A refeição ainda não está pronta para recebimento.</p><button onClick={consultarNovamente} className={BOTAO}>Consultar novamente</button></div>}
        {erro && <button onClick={consultarNovamente} disabled={enviando} className="min-h-12 w-full rounded-lg bg-slate-50 px-4 py-3 font-semibold">Consultar novamente</button>}
      </>}
    </section>
  </main>
}
