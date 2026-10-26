import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { mensagemErro } from '../services/painelOperacional.js'
import { CAMPO, PRIMARIO, FiltroUnidade } from './ConsultaGestao.jsx'

export default function ConfiguracaoAlertas({ filiais = [], filialId }) {
  const [selecionada, setSelecionada] = useState(String(filiais[0]?.id || ''))
  const alvo = filialId || selecionada
  return <section className="space-y-4 rounded-xl bg-panel p-4 sm:p-6">
    <div><h2 className="text-xl font-bold">Alertas de demora</h2><p className="mt-1 text-sm text-slate-700">Defina os prazos desta unidade. Os cartões da cozinha e das entregas destacam refeições que ultrapassarem esses tempos.</p></div>
    {!filialId && <FiltroUnidade filiais={filiais} valor={selecionada} onChange={setSelecionada} todas={false} />}
    {alvo ? <EditorAlertas key={alvo} filialId={alvo} /> : <p>Selecione uma unidade.</p>}
  </section>
}

function EditorAlertas({ filialId }) {
  const [form, setForm] = useState(null)
  const [erro, setErro] = useState('')
  const [sucesso, setSucesso] = useState('')
  const [salvando, setSalvando] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    api.get(`/gestao/alertas/${filialId}`, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setForm(data) })
      .catch((e) => { if (!controller.signal.aborted) setErro(mensagemErro(e)) })
    return () => controller.abort()
  }, [filialId])
  async function salvar(e) {
    e.preventDefault(); setSalvando(true); setErro(''); setSucesso('')
    try {
      const dados = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === null ? null : Number(v)]))
      const { data } = await api.put(`/gestao/alertas/${filialId}`, dados)
      setForm(data); setSucesso('Prazos salvos. Os painéis serão atualizados automaticamente.')
    } catch (e) { setErro(mensagemErro(e)) } finally { setSalvando(false) }
  }
  return <>
    {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{erro}</p>}
    {sucesso && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-emerald-900">{sucesso}</p>}
    {form ? <form onSubmit={salvar} className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        {[
          ['preparo_minutos', 'Solicitação até refeição pronta', 'Conta desde a solicitação, incluindo a espera e o preparo.'],
          ['entrega_minutos', 'Refeição pronta até entrega', 'Conta desde que a cozinha marca a refeição como pronta.'],
        ].map(([chave, titulo, descricao]) => <fieldset key={chave} className="min-w-0 space-y-3 rounded-lg border border-slate-300 p-4">
          <legend className="px-1 font-semibold">{titulo}</legend>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form[chave] !== null} disabled={salvando}
            onChange={(e) => { setForm({ ...form, [chave]: e.target.checked ? '' : null }); setSucesso('') }} />Ativar alerta</label>
          <label className="block text-sm font-semibold">Prazo em minutos
            <input type="number" min={1} max={1440} step={1} required={form[chave] !== null} disabled={salvando || form[chave] === null}
              className={CAMPO} value={form[chave] ?? ''} onChange={(e) => { setForm({ ...form, [chave]: e.target.value }); setSucesso('') }} />
          </label><p className="text-sm text-slate-700">{descricao}</p>
        </fieldset>)}
      </div><p className="text-sm text-slate-700">Desative um alerta para não aplicar prazo nessa etapa. Os tempos não alteram o status dos pedidos.</p>
      <button className={PRIMARIO} disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar prazos'}</button>
    </form> : !erro && <p>Carregando prazos…</p>}
  </>
}
