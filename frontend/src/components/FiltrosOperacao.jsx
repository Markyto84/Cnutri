import { useId, useState } from 'react'
import { FILTROS_VAZIOS } from '../services/painelOperacional.js'
import { BOTAO } from './Operacao.jsx'

export default function FiltrosOperacao({ pedidos, filtros, onChange, total }) {
  const [aberto, setAberto] = useState(false)
  const id = useId()
  const campos = [
    ['andar', 'Andar / setor', (p) => p.dados_dinamicos?.andar],
    ['leito', 'Leito', (p) => p.leito],
    ['refeicao', 'Refeição', (p) => p.dados_dinamicos?.refeicao],
  ]
  const mudar = (campo, valor) => onChange({ ...filtros, [campo]: valor })
  const estilo = 'mt-1 min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-sm font-normal'
  return <section aria-label="Filtros de refeições" className="mb-4 rounded-xl bg-panel p-4">
    <button className={`${BOTAO} mb-2 w-full bg-white md:hidden`} aria-expanded={aberto} aria-controls={id} onClick={() => setAberto(!aberto)}>{aberto ? 'Ocultar filtros' : 'Mostrar filtros'}</button>
    <div id={id} className={`${aberto ? 'grid' : 'hidden'} min-w-0 gap-3 sm:grid-cols-2 md:grid lg:grid-cols-5`}>
      <label className="min-w-0 text-sm font-semibold">Buscar pedido, nome ou leito
        <input type="search" maxLength={100} className={estilo} value={filtros.busca} onChange={(e) => mudar('busca', e.target.value)} placeholder="Ex.: #123, Maria, 402" />
      </label>
      {campos.map(([chave, titulo, obter]) => {
        const opcoes = [...new Set([...pedidos.map(obter), filtros[chave]].filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR', { numeric: true }))
        return <label key={chave} className="min-w-0 text-sm font-semibold">{titulo}
          <select className={estilo} value={filtros[chave]} onChange={(e) => mudar(chave, e.target.value)}><option value="">Todos</option>
            {opcoes.map((opcao) => <option key={opcao} value={opcao}>{opcao}</option>)}
          </select></label>
      })}
      <label className="min-w-0 text-sm font-semibold">Tipo de formulário
        <select className={estilo} value={filtros.tipo} onChange={(e) => mudar('tipo', e.target.value)}>
          <option value="">Todos</option><option value="PACIENTE">Paciente / Enfermagem</option><option value="MEDICO">Médico / Administração</option>
        </select></label>
    </div>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <p role="status" className="text-sm text-slate-700">Exibindo {total} de {pedidos.length} refeição(ões)</p>
      <button className={`${BOTAO} bg-white`} onClick={() => onChange({ ...FILTROS_VAZIOS })}>Limpar filtros</button>
    </div>
  </section>
}
