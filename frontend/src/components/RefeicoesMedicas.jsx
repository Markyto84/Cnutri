import { useEffect, useState } from 'react'
import { api } from '../services/api.js'

const LISTAS_EDITAVEIS = [
  { id: 'refeicao', rotulo: 'Refeição' },
  { id: 'suco', rotulo: 'Suco' },
  { id: 'sobremesa', rotulo: 'Sobremesa' },
  { id: 'local_entrega', rotulo: 'Local de entrega' },
]

export default function RefeicoesMedicas({ filialId }) {
  const [config, setConfig] = useState(null)
  const [textos, setTextos] = useState({})
  const [carregando, setCarregando] = useState(true)
  const [salvando, setSalvando] = useState(false)
  const [conflito, setConflito] = useState(false)
  const [erro, setErro] = useState(null)
  const [sucesso, setSucesso] = useState(null)
  const [revisao, setRevisao] = useState(0)
  const endpoint = `/gestao/formularios/${filialId}/MEDICO`

  useEffect(() => {
    const controller = new AbortController()
    api.get(endpoint, { signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        const listas = Object.fromEntries(LISTAS_EDITAVEIS.map(({ id, rotulo }) => {
          const campo = data?.esquema_json?.campos?.find((c) => c.id === id && c.tipo === 'selecao')
          if (!campo) throw new Error(`O campo ${rotulo} precisa estar configurado no formulário médico.`)
          return [id, (campo.opcoes || []).join('\n')]
        }))
        setConfig(data)
        setTextos(listas)
        setConflito(false)
      })
      .catch((e) => {
        if (controller.signal.aborted) return
        setConfig(null)
        setErro(e.response?.data?.detail || e.message || 'Erro ao carregar as opções do formulário médico.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setCarregando(false)
      })
    return () => controller.abort()
  }, [endpoint, revisao])

  function recarregar() {
    setCarregando(true)
    setErro(null)
    setSucesso(null)
    setRevisao((valor) => valor + 1)
  }

  async function salvar(e) {
    e.preventDefault()
    if (!config || conflito || salvando) return
    setErro(null)
    setSucesso(null)
    const opcoesPorCampo = {}
    for (const { id, rotulo } of LISTAS_EDITAVEIS) {
      const opcoes = (textos[id] || '').split('\n').map((linha) => linha.trim()).filter(Boolean)
      if (opcoes.length === 0) {
        setErro(`Informe pelo menos uma opção em ${rotulo}.`)
        return
      }
      if (new Set(opcoes).size !== opcoes.length) {
        setErro(`Há opções repetidas em ${rotulo}. Revise a lista antes de salvar.`)
        return
      }
      opcoesPorCampo[id] = opcoes
    }

    setSalvando(true)
    try {
      const esquema = config.esquema_json
      const campos = esquema.campos.map((c) => Object.hasOwn(opcoesPorCampo, c.id)
        ? { ...c, opcoes: opcoesPorCampo[c.id] }
        : c)
      const { data } = await api.put(endpoint, {
        esquema_json: { ...esquema, campos },
        versao: config.atualizado_em,
      })
      setConfig(data)
      setTextos(Object.fromEntries(Object.entries(opcoesPorCampo).map(([id, opcoes]) => [id, opcoes.join('\n')])))
      setSucesso('Opções do formulário médico atualizadas.')
    } catch (e) {
      if (e.response?.status === 409) setConflito(true)
      setErro(e.response?.data?.detail || 'Erro ao salvar as opções do formulário médico.')
    } finally {
      setSalvando(false)
    }
  }

  return (
    <form onSubmit={salvar} className="max-w-5xl space-y-4 rounded-xl bg-panel p-6">
      <div>
        <h2 className="text-xl font-bold">Refeições e opções do formulário médico</h2>
        <p className="mt-1 text-sm text-slate-700">
          Edite as refeições, os sucos, as sobremesas e os locais de entrega. Cadastre uma opção por linha em cada campo.
        </p>
      </div>
      {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
      {sucesso && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{sucesso}</p>}
      {carregando ? <p className="text-sm text-slate-700">Carregando opções…</p> : config && (
        <div className="grid gap-4 md:grid-cols-3">
          {LISTAS_EDITAVEIS.map(({ id, rotulo }) => (
            <div key={id} className={id === 'refeicao' ? 'md:col-span-3' : ''}>
              <label htmlFor={`medico-${id}`} className="mb-2 block text-sm font-medium">{rotulo}</label>
              <textarea
                id={`medico-${id}`}
                rows={3}
                value={textos[id] || ''}
                onChange={(e) => { setTextos((atuais) => ({ ...atuais, [id]: e.target.value })); setSucesso(null) }}
                disabled={salvando}
                className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-brand disabled:opacity-50"
              />
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={carregando || salvando || !config || conflito}
          className="rounded-lg bg-brand px-5 py-2 font-bold text-white hover:bg-brand-hover disabled:opacity-50"
        >
          {salvando ? 'Salvando…' : 'Salvar opções'}
        </button>
        <button
          type="button"
          onClick={recarregar}
          disabled={carregando || salvando}
          className="rounded-lg bg-slate-50 px-4 py-2 hover:bg-slate-200 disabled:opacity-50"
        >Recarregar opções</button>
      </div>
    </form>
  )
}
