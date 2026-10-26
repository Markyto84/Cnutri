import { useState } from 'react'
import { dataBrasilia, horarioBrasilia } from '../services/painelOperacional.js'
import { CAMPO, SECUNDARIO, FiltroUnidade, Paginacao } from './ConsultaGestao.jsx'
import { useConsultaGestao } from '../hooks/useConsultaGestao.js'

const ENTIDADES = { UNIDADE: 'Unidade', CREDENCIAL: 'Credencial / permissão', DIETA: 'Dieta', FORMULARIO: 'Formulário / cardápio', IMPRESSORA_FILIPETA: 'Impressora de filipetas', IMPRESSORA_ETIQUETA: 'Impressora de etiquetas', ALERTAS: 'Alertas de demora' }
const ACOES = { CRIAR: 'Criação', ALTERAR: 'Alteração', DESATIVAR: 'Desativação', REDEFINIR_SENHA: 'Redefinição de senha', TROCAR_SENHA: 'Troca da própria senha' }
const ROTULOS = { nome: 'Nome', nome_usuario: 'Usuário', codigo_slug: 'Código da unidade', ativa: 'Ativa', ativo: 'Ativo', perfil: 'Perfil', filial_ids: 'Unidades permitidas (IDs)', origem_autenticacao: 'Autenticação', usuario_ad: 'Usuário AD', ip_impressora: 'IP da impressora', esquema_json: 'Formulário e cardápios', tipo_publico: 'Tipo do formulário', preparo_minutos: 'Prazo de preparo (min)', entrega_minutos: 'Prazo de entrega (min)', senha_redefinida: 'Senha temporária redefinida', senha_alterada: 'Senha alterada', troca_senha_obrigatoria: 'Troca de senha obrigatória' }
function mostrar(valor) {
  if (valor === null || valor === undefined) return 'Não definido'
  if (typeof valor === 'boolean') return valor ? 'Sim' : 'Não'
  return typeof valor === 'object' ? JSON.stringify(valor, null, 2) : String(valor)
}

export default function HistoricoAdministrativo({ filiais = [], filialId, administrador = false }) {
  const [filtros, setFiltros] = useState(() => ({ filial_id: '', entidade: '', inicio: dataBrasilia(Date.now() - 6 * 86400000), fim: dataBrasilia() }))
  const [pagina, setPagina] = useState(1)
  const params = Object.fromEntries(Object.entries({ ...filtros, filial_id: filialId || filtros.filial_id, pagina }).filter(([, v]) => v !== ''))
  const consulta = useConsultaGestao('/gestao/auditoria', params)
  function mudar(chave, valor) { setFiltros((f) => ({ ...f, [chave]: valor })); setPagina(1) }
  return <section className="min-w-0 space-y-4" aria-label="Histórico administrativo">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-bold">Histórico de alterações</h2>
      <p className="mt-1 text-sm text-slate-700">Autor, data e valores alterados. O registro começa com esta atualização; alterações anteriores não são reconstruídas.</p></div>
      <button className={SECUNDARIO} onClick={consulta.atualizar}>Atualizar histórico</button></div>
    <div className="grid min-w-0 gap-3 rounded-xl bg-panel p-4 sm:grid-cols-2 xl:grid-cols-4">
      {!filialId && <FiltroUnidade filiais={filiais} valor={filtros.filial_id} onChange={(v) => mudar('filial_id', v)} />}
      <label className="min-w-0 text-sm font-semibold">Cadastro alterado<select className={CAMPO} value={filtros.entidade} onChange={(e) => mudar('entidade', e.target.value)}>
        <option value="">Todos</option>{Object.entries(ENTIDADES).filter(([id]) => administrador || id !== 'CREDENCIAL').map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}</select></label>
      <label className="min-w-0 text-sm font-semibold">Data inicial<input type="date" className={CAMPO} value={filtros.inicio} onChange={(e) => mudar('inicio', e.target.value)} /></label>
      <label className="min-w-0 text-sm font-semibold">Data final<input type="date" className={CAMPO} value={filtros.fim} onChange={(e) => mudar('fim', e.target.value)} /></label>
    </div>
    {consulta.erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-900">{consulta.erro}</p>}
    {consulta.carregando && <p>Carregando histórico…</p>}
    {consulta.dados && <><Paginacao {...consulta.dados} onChange={setPagina} />
      {!consulta.dados.itens.length && <p className="rounded-xl bg-panel p-6">Nenhuma alteração registrada neste período e nestes filtros.</p>}
      <div className="space-y-3">{consulta.dados.itens.map((item) => {
        const unidade = filiais.find((f) => f.id === item.filial_id)
        const campos = [...new Set([...Object.keys(item.antes || {}), ...Object.keys(item.depois || {})])]
        return <article key={item.id} className="min-w-0 space-y-3 rounded-xl bg-panel p-4">
          <h3 className="break-words font-bold">{ENTIDADES[item.entidade] || item.entidade} #{item.entidade_id} · {ACOES[item.acao] || item.acao}</h3>
          <p className="text-sm text-slate-700">{horarioBrasilia(item.criado_em)} · {item.autor_nome} · {unidade?.nome || (item.filial_id ? `Unidade #${item.filial_id}` : 'Administração global')}</p>
          <details className="min-w-0"><summary className="min-h-11 cursor-pointer py-2 font-semibold text-brand">Ver alterações ({campos.length})</summary>
            <div className="space-y-3 pt-2">{campos.map((campo) => <div key={campo} className="min-w-0 rounded-lg bg-white p-3">
              <h4 className="mb-2 break-words font-semibold">{ROTULOS[campo] || campo}</h4>
              <div className="grid min-w-0 gap-3 md:grid-cols-2"><div className="min-w-0"><p className="text-xs font-bold text-slate-700">ANTES</p><pre className="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm">{mostrar(item.antes?.[campo])}</pre></div>
                <div className="min-w-0"><p className="text-xs font-bold text-slate-700">DEPOIS</p><pre className="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-sm">{mostrar(item.depois?.[campo])}</pre></div></div>
            </div>)}</div>
          </details>
        </article>
      })}</div></>}
  </section>
}
