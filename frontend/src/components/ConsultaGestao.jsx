export const CAMPO = 'mt-1 min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-sm font-normal'
export const PRIMARIO = 'ui-button ui-button-primary'
export const SECUNDARIO = 'ui-button ui-button-secondary'

export function FiltroUnidade({ filiais, valor, onChange, todas = true }) {
  return <label className="min-w-0 text-sm font-semibold">Unidade
    <select className={CAMPO} value={valor} onChange={(e) => onChange(e.target.value)}>
      {todas && <option value="">Todas as unidades permitidas</option>}
      {filiais.map((f) => <option key={f.id} value={f.id}>{f.nome} · {f.codigo_slug}{f.ativa ? '' : ' (inativa)'}</option>)}
    </select>
  </label>
}

export function Paginacao({ pagina, total, tamanho, onChange }) {
  const paginas = Math.max(1, Math.ceil(total / tamanho))
  return <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
    <p role="status">{total} registro(s) · Página {pagina} de {paginas}</p>
    <div className="flex gap-2"><button className={SECUNDARIO} disabled={pagina <= 1} onClick={() => onChange(pagina - 1)}>Anterior</button>
      <button className={SECUNDARIO} disabled={pagina >= paginas} onClick={() => onChange(pagina + 1)}>Próxima</button></div>
  </div>
}
