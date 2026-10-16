/** Renderiza o formulário dinâmico definido pela Nutrição (motor de formulários). */
import { useEffect, useState } from 'react'

export default function FormDinamico({ titulo, cabecalho, campos, dietas, enviando, erro, onCancelar, onEnviar }) {
  const [valores, setValores] = useState({})

  const setValor = (id, v) => setValores((a) => ({ ...a, [id]: v }))

  // Nome da dieta selecionada (para campos dependentes, ex.: cardápio)
  const dietaNome = dietas.find((d) => d.id === Number(valores.dieta_id))?.nome || ''

  // Ao trocar a dieta, limpa valores de campos cardápio que não pertencem ao novo grupo
  useEffect(() => {
    for (const campo of campos.filter((c) => c.tipo === 'cardapio')) {
      const grupo = (campo.grupos || []).find((g) => (g.dietas || []).includes(dietaNome))
      const opcoes = grupo?.opcoes || []
      const atual = valores[campo.id]
      if (atual && !opcoes.includes(atual)) setValor(campo.id, '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dietaNome])

  function opcoesCardapio(campo) {
    const grupo = (campo.grupos || []).find((g) => (g.dietas || []).includes(dietaNome))
    return grupo?.opcoes || []
  }

  function submeter(e) {
    e.preventDefault()
    onEnviar(valores)
  }

  return (
    <form onSubmit={submeter} className="mx-auto max-w-2xl space-y-5 rounded-2xl bg-slate-800 p-8 shadow-xl">
      <h2 className="text-2xl font-bold text-white">{titulo}</h2>

      {cabecalho && (
        <div className="whitespace-pre-line rounded-lg bg-slate-700/60 p-4 text-sm leading-relaxed text-slate-300">
          {cabecalho}
        </div>
      )}

      {erro && <div className="rounded-lg bg-red-900/50 p-3 text-red-300 text-sm">{erro}</div>}

      {campos.map((campo) => (
        <div key={campo.id}>
          <label className="mb-1 block text-sm font-medium text-slate-300">
            {campo.rotulo}
            {campo.obrigatorio && <span className="text-red-400"> *</span>}
          </label>

          {campo.tipo === 'texto' && (
            <input
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
              required={campo.obrigatorio}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'texto_longo' && (
            <textarea
              rows={3}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'data' && (
            <input
              type="date"
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
              required={campo.obrigatorio}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'selecao' && (
            <select
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
              required={campo.obrigatorio}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            >
              <option value="">— Selecionar —</option>
              {(campo.opcoes || []).map((op) => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>
          )}

          {campo.tipo === 'cardapio' && (() => {
            const opcoes = opcoesCardapio(campo)
            if (!dietaNome) {
              return (
                <select disabled className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-4 py-3 text-slate-400">
                  <option>Selecione o Tipo de Dieta para ver o cardápio…</option>
                </select>
              )
            }
            if (opcoes.length === 0) {
              return (
                <select disabled className="w-full rounded-lg border border-slate-600 bg-slate-700/50 px-4 py-3 text-slate-400">
                  <option>Sem cardápio configurado para esta dieta</option>
                </select>
              )
            }
            return (
              <select
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
                required={campo.obrigatorio}
                value={valores[campo.id] || ''}
                onChange={(e) => setValor(campo.id, e.target.value)}
              >
                <option value="">— Selecionar —</option>
                {opcoes.map((op) => (
                  <option key={op} value={op}>{op}</option>
                ))}
              </select>
            )
          })()}

          {campo.tipo === 'selecao_dietas' && (
            <select
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white outline-none focus:border-blue-400"
              required={campo.obrigatorio}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            >
              <option value="">— Selecionar —</option>
              {dietas.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.nome}{d.severa ? ' ⚠️' : ''}
                </option>
              ))}
            </select>
          )}
        </div>
      ))}

      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={onCancelar}
          className="rounded-lg bg-slate-600 px-6 py-3 font-medium hover:bg-slate-500"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={enviando}
          className="flex-1 rounded-lg bg-blue-600 px-6 py-3 text-lg font-bold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {enviando ? 'A enviar…' : 'Enviar Solicitação'}
        </button>
      </div>
    </form>
  )
}
