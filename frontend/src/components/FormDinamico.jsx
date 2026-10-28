/** Renderiza o formulário dinâmico definido pela Nutrição (motor de formulários). */
import { useState } from 'react'
import { ajustarValores, campoVisivel, dietasDisponiveis, erroAcompanhante, erroLiquidos, opcoesCardapio } from '../services/formularioPaciente.js'

export default function FormDinamico({ titulo, cabecalho, destacarCabecalho = false, etapa, campos, dietas, enviando, erro, onCancelar, onEnviar,
  valoresIniciais = {}, complemento, textoBotao = 'Enviar Solicitação' }) {
  const [valores, setValores] = useState(() => ajustarValores(campos, dietas, valoresIniciais))

  const setValor = (id, v) => setValores((a) => ajustarValores(campos, dietas, { ...a, [id]: v }))

  // Nome da dieta selecionada (para campos dependentes, ex.: cardápio)
  const dietaNome = dietas.find((d) => d.id === Number(valores.dieta_id))?.nome || ''

  const avisoAcompanhante = erroAcompanhante(campos, dietas, valores)
  const avisoLiquidos = erroLiquidos(campos, valores)

  function submeter(e) {
    e.preventDefault()
    if (!avisoAcompanhante && !avisoLiquidos) onEnviar(ajustarValores(campos, dietas, valores))
  }

  return (
    <form onSubmit={submeter} className="form-card mx-auto space-y-5 rounded-2xl bg-panel p-5 sm:p-7">
      <div className="form-card-heading">{etapa && <span className="form-step">{etapa}</span>}<div><h2>{titulo}</h2><p>Confira os dados para ajudar a equipe no preparo e na entrega.</p></div></div>

      {cabecalho && (
        destacarCabecalho || cabecalho.length < 300
          ? <div className="whitespace-pre-line rounded-xl bg-brand-soft p-4 text-sm leading-relaxed text-brand-ink">{destacarCabecalho ? <strong>{cabecalho}</strong> : cabecalho}</div>
          : <details open className="orientacoes-unidade rounded-xl bg-slate-50 text-sm text-slate-700">
            <summary className="cursor-pointer px-4 py-3 font-semibold text-brand-ink">Horários e orientações da unidade</summary>
            <div className="whitespace-pre-line border-t border-slate-200 px-4 py-4 leading-relaxed">{cabecalho}</div>
          </details>
      )}

      {erro && <div role="alert" className="rounded-lg bg-red-50 p-3 text-red-800 text-sm">{erro}</div>}

      <div className="dynamic-fields">
      {campos.filter((campo) => campoVisivel(campo, valores)).map((campo) => (
        <div key={campo.id} className={`form-field ${['radio', 'texto_longo', 'cardapio', 'selecao_dietas'].includes(campo.tipo) || ['nome_paciente', 'solicitante_nome', 'refeicao', 'local_entrega'].includes(campo.id) ? 'form-field-wide' : ''}`}>
          {campo.tipo === 'radio' ? (
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-slate-700">
                {campo.rotulo}
                {campo.obrigatorio && <span className="text-red-700"> *</span>}
              </legend>
              <div className="flex flex-wrap gap-3">
                {(campo.opcoes || []).map((op) => (
                  <label
                    key={op}
                    className={`radio-choice flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-3 text-sm text-slate-900 ${
                      valores[campo.id] === op
                        ? 'border-brand bg-brand-soft'
                        : 'border-slate-300 bg-slate-50 hover:bg-slate-100'
                    }`}
                  >
                    <input
                      type="radio"
                      name={campo.id}
                      value={op}
                      checked={valores[campo.id] === op}
                      required={campo.obrigatorio}
                      onChange={(e) => setValor(campo.id, e.target.value)}
                      className="h-4 w-4 accent-brand"
                    />
                    {op}
                  </label>
                ))}
              </div>
            </fieldset>
          ) : (
            <label htmlFor={campo.id} className="mb-1 block text-sm font-medium text-slate-700">
              {campo.rotulo}
              {campo.obrigatorio && <span className="text-red-700"> *</span>}
            </label>
          )}

          {campo.tipo === 'texto' && (
            <input
              maxLength={({ leito: 30, prontuario: 50, nome_paciente: 100, solicitante_nome: 100 })[campo.id] || 1000}
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              required={campo.obrigatorio}
              id={campo.id}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'texto_longo' && (
            <textarea
              required={campo.obrigatorio}
              id={campo.id}
              maxLength={5000}
              rows={3}
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'data' && (
            <input
              type="date"
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              required={campo.obrigatorio}
              id={campo.id}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            />
          )}

          {campo.tipo === 'selecao' && (
            <select
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              required={campo.obrigatorio}
              id={campo.id}
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
            const opcoes = opcoesCardapio(campo, dietaNome)
            if (!dietaNome && !campo.dieta_fixa) {
              return (
                <select id={campo.id} disabled className="w-full rounded-lg border border-slate-300 bg-slate-100 px-4 py-3 text-slate-600">
                  <option>Selecione o Tipo de Dieta para ver o cardápio…</option>
                </select>
              )
            }
            if (opcoes.length === 0) {
              return (
                <select id={campo.id} disabled className="w-full rounded-lg border border-slate-300 bg-slate-100 px-4 py-3 text-slate-600">
                  <option>Sem cardápio configurado para esta dieta</option>
                </select>
              )
            }
            return (
              <select
                className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
                required={campo.obrigatorio}
                id={campo.id}
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
              className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
              required={campo.obrigatorio}
              id={campo.id}
              value={valores[campo.id] || ''}
              onChange={(e) => setValor(campo.id, e.target.value)}
            >
              <option value="">— Selecionar —</option>
              {dietasDisponiveis(campos, dietas, valores).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.nome}{d.severa ? ' ⚠️' : ''}
                </option>
              ))}
            </select>
          )}
          {['selecao', 'cardapio'].includes(campo.tipo) && String(valores[campo.id] || '').length > 48 && <p aria-hidden="true" className="mt-2 text-sm leading-relaxed text-slate-700">{valores[campo.id]}</p>}
          {campo.id === 'dieta_id' && avisoAcompanhante && <p role="alert" className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{avisoAcompanhante}</p>}
          {campo.id === 'tipo_liquido_espessado' && avisoLiquidos && <p role="alert" className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{avisoLiquidos}</p>}
        </div>
      ))}
      </div>

      {complemento?.(valores)}
      <div className="form-actions flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onCancelar}
          className="ui-button ui-button-secondary"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={enviando || !!avisoAcompanhante || !!avisoLiquidos}
          className="ui-button ui-button-primary min-w-40 flex-1"
        >
          {enviando ? 'Enviando…' : textoBotao}
        </button>
      </div>
    </form>
  )
}
