import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/auth.js'

export const BOTAO = 'min-h-11 rounded-lg px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50'

export function CabecalhoOperacao({ modo, painel, filialId }) {
  const navegar = useNavigate()
  const { usuario, sair, plantaoOnline } = useAuth()
  const entrega = modo === 'entregas'
  const minhas = usuario?.perfil === 'COPEIRA' ? painel.filiais.filter((f) => usuario.filiais.some((u) => u.id === f.id)) : painel.filiais
  const nestePlantao = usuario?.perfil === 'COPEIRA' && usuario.filiais.some((f) => f.id === Number(filialId))
  return <header className="brand-header mb-5 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><h1 className="text-xl font-bold text-brand sm:text-2xl">{entrega ? 'Entrega de refeições' : 'Dashboard da cozinha'}</h1>
        <p className="mt-1 text-sm text-slate-700">{painel.filial?.nome || 'Carregando unidade…'}</p></div>
      <span className="rounded-full bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700">{painel.conectado ? '● Atualização ao vivo' : 'Atualização automática'}</span>
    </div>
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
      <select aria-label="Unidade do painel" className="col-span-2 min-h-11 min-w-0 rounded-lg border border-slate-300 bg-slate-50 px-3 text-base sm:max-w-xs sm:text-sm" value={filialId} onChange={(e) => navegar(`/${modo}/${e.target.value}`)}>
        {!minhas.some((f) => f.id === Number(filialId)) && <option value={filialId}>{painel.filial?.nome || 'Unidade'}</option>}
        {minhas.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
      </select>
      <Link to={`/${entrega ? 'cozinha' : 'entregas'}/${filialId}`} className={`${BOTAO} text-center ${entrega ? 'bg-slate-50 text-slate-900' : 'bg-brand-vibrant text-brand-ink hover:bg-brand-vibrant-hover'}`}>{entrega ? 'Dashboard da cozinha' : 'Entregas das copeiras'}</Link>
      <button onClick={() => painel.recarregar()} className={`${BOTAO} bg-slate-50 text-slate-900`}>Atualizar</button>
      {usuario?.perfil === 'ADMIN_TI' && <Link to="/admin" className={`${BOTAO} bg-slate-50 text-center`}>Administração</Link>}
      {usuario?.perfil === 'NUTRICIONISTA' && <Link to={`/gestao?unidade=${filialId}`} className={`${BOTAO} bg-slate-50 text-center`}>Gestão</Link>}
      {!usuario && <Link to={`/login?retorno=${encodeURIComponent(`/${modo}/${filialId}`)}`} className={`${BOTAO} col-span-2 bg-brand text-center text-white hover:bg-brand-hover`}>{entrega ? 'Entrar no plantão' : 'Entrar para operar'}</Link>}
      {usuario && <Link to={`/senha?retorno=${encodeURIComponent(`/${modo}/${filialId}`)}`} className={`${BOTAO} bg-slate-50 text-center`}>{usuario.troca_senha_obrigatoria ? 'Definir nova senha' : 'Alterar minha senha'}</Link>}
      {usuario && <button onClick={sair} className={`${BOTAO} col-span-2 bg-slate-50 text-slate-900`}>Sair{usuario.perfil === 'COPEIRA' ? ' do plantão' : ''}</button>}
    </div>
    {usuario?.perfil === 'COPEIRA' && <p role="status" className={`rounded-lg p-3 text-sm ${nestePlantao && plantaoOnline ? 'bg-emerald-50 text-emerald-900' : 'bg-amber-50 text-amber-900'}`}>
      <strong>{usuario.nome}</strong> · {nestePlantao && plantaoOnline ? 'Você está online neste plantão' : 'Sua presença depende de conexão e vínculo com esta unidade'}
    </p>}
    {!usuario && <p className="rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Consulta pública por número e etapa. Entre com uma conta vinculada à unidade para visualizar destinatários, dietas e locais de entrega.</p>}
  </header>
}

export function ResumoPedido({ pedido }) {
  const dados = pedido.dados_dinamicos || {}
  const severa = pedido.dieta?.severa || /alergi|sever/i.test(pedido.observacoes_alergias || '')
  return <div className="min-w-0 space-y-3 break-words">
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-700">
      <span>Pedido #{pedido.id} · {pedido.tipo_solicitacao === 'MEDICO' ? 'Profissional' : 'Paciente'}</span>
      {severa && <strong className="rounded bg-red-700 px-2 py-1 text-white">RESTRIÇÃO / ALERGIA</strong>}
    </div>
    <p className="text-lg font-bold leading-snug">{pedido.nome_paciente || pedido.solicitante_nome || `Solicitação #${pedido.id}`}
      {pedido.idade != null && <span className="ml-2 text-sm font-normal text-slate-700">{pedido.idade} anos</span>}</p>
    <div className="flex flex-wrap gap-2 text-sm">
      {pedido.leito && <span className="rounded bg-slate-100 px-2 py-1">Leito {pedido.leito}</span>}
      {(dados.andar || dados.local_entrega) && <span className="rounded bg-slate-100 px-2 py-1">{dados.andar || dados.local_entrega}</span>}
      {dados.horario_entrega && <span className="rounded bg-brand-soft px-2 py-1 text-brand-ink">Entrega: {dados.horario_entrega}</span>}
    </div>
    {dados.refeicao && <p className="font-semibold text-brand-ink">{dados.refeicao}</p>}
    {pedido.dieta && <p className="text-sm"><strong>Dieta:</strong> {pedido.dieta.nome}</p>}
    {dados.cardapio && <p className="text-sm"><strong>Cardápio:</strong> {dados.cardapio}</p>}
    {dados.cardapio_acompanhante && <p className="text-sm"><strong>Cardápio do acompanhante (GERAL):</strong> {dados.cardapio_acompanhante}</p>}
    <div className="flex flex-wrap gap-2 text-xs text-slate-700">{[dados.equipe, dados.para, dados.suco, dados.sobremesa, dados.liquido_espessado && `Líquido espessado: ${dados.liquido_espessado}${dados.tipo_liquido_espessado ? ` · ${dados.tipo_liquido_espessado}` : ''}`].filter(Boolean).map((item, i) => <span key={i} className="rounded bg-slate-50 px-2 py-1">{item}</span>)}</div>
    {pedido.observacoes_alergias && <p className="whitespace-pre-line rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{pedido.observacoes_alergias}</p>}
  </div>
}
