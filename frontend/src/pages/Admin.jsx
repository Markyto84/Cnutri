import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api.js'
import { useAuth } from '../context/auth.js'
import RelatorioDietas from '../components/RelatorioDietas.jsx'

const CAMPO = 'w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-slate-900 outline-none focus:border-blue-600'
const PRIMARIO = 'rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-500 disabled:opacity-50'
const SECUNDARIO = 'rounded-lg bg-slate-50 px-4 py-2 text-sm hover:bg-slate-200 disabled:opacity-50'
const PERFIS = { ADMIN_TI: 'Administrador', NUTRICIONISTA: 'Gestor de nutrição', COZINHA: 'Cozinha', COPEIRA: 'Copeira' }

function mensagemErro(e) {
  const detalhe = e.response?.data?.detail
  return typeof detalhe === 'string' ? detalhe : Array.isArray(detalhe)
    ? detalhe.map((d) => d.msg).join('; ') : 'Não foi possível concluir a operação. Tente novamente.'
}

function Campo({ titulo, children }) {
  return <label className="block text-sm font-medium"><span className="mb-1 block">{titulo}</span>{children}</label>
}

function Aviso({ erro, sucesso }) {
  return <>{erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</p>}
    {sucesso && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{sucesso}</p>}</>
}

export default function Admin() {
  const { usuario, sair, atualizarUsuario } = useAuth()
  const [aba, setAba] = useState('unidades')
  const [dados, setDados] = useState({ filiais: [], usuarios: [] })
  const [carregando, setCarregando] = useState(true)
  const [revisao, setRevisao] = useState(0)
  const [erro, setErro] = useState(null)
  const [sucesso, setSucesso] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([api.get('/admin/filiais', { signal: controller.signal }), api.get('/admin/usuarios', { signal: controller.signal })])
      .then(([filiais, usuarios]) => { if (!controller.signal.aborted) setDados({ filiais: filiais.data, usuarios: usuarios.data }) })
      .catch((e) => { if (!controller.signal.aborted) setErro(mensagemErro(e)) })
      .finally(() => { if (!controller.signal.aborted) setCarregando(false) })
    return () => controller.abort()
  }, [revisao])

  function concluido(mensagem) {
    setErro(null)
    setSucesso(mensagem)
    setRevisao((r) => r + 1)
    atualizarUsuario().catch(() => setErro('Cadastro salvo. Recarregue a página para atualizar suas unidades.'))
  }

  return <div className="min-h-screen space-y-6 bg-app-background p-6 text-slate-900">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div><h1 className="text-2xl font-bold">⚙️ Painel de administração</h1>
        <p className="mt-1 text-sm text-slate-950">Unidades, credenciais e impressoras · {usuario.nome}</p></div>
      <div className="flex flex-wrap gap-2"><Link to="/gestao" className={SECUNDARIO}>Gestão de nutrição</Link>
        <button onClick={sair} className={SECUNDARIO}>Sair</button></div>
    </header>
    <div className="grid gap-4 sm:grid-cols-3">
      {[
        ['Unidades cadastradas', dados.filiais.length],
        ['Credenciais ativas', dados.usuarios.filter((u) => u.ativo).length],
        ['Impressoras configuradas', dados.filiais.filter((f) => f.ip_impressora).length],
      ].map(([rotulo, total]) => <div key={rotulo} className="rounded-xl bg-panel p-4"><p className="text-sm text-slate-700">{rotulo}</p><p className="mt-1 text-3xl font-bold">{total}</p></div>)}
    </div>
    <nav className="flex flex-wrap gap-2" aria-label="Administração">
      {[['unidades', '🏢 Unidades'], ['credenciais', '🔑 Credenciais'], ['impressoras', '🖨️ Impressoras'], ['relatorios', '📊 Relatórios']].map(([id, rotulo]) =>
        <button key={id} onClick={() => { setAba(id); setErro(null); setSucesso(null) }} className={aba === id ? PRIMARIO : SECUNDARIO}>{rotulo}</button>)}
    </nav>
    <Aviso erro={erro} sucesso={sucesso} />
    {carregando ? <p>Carregando administração…</p> : <>
      {aba === 'unidades' && <Unidades filiais={dados.filiais} onConcluido={concluido} />}
      {aba === 'credenciais' && <Credenciais filiais={dados.filiais} usuarios={dados.usuarios} usuarioAtual={usuario} onConcluido={concluido} />}
      {aba === 'impressoras' && <Impressoras filiais={dados.filiais} onConcluido={concluido} />}
      {aba === 'relatorios' && <RelatorioDietas filiais={dados.filiais} />}
    </>}
  </div>
}

function Unidades({ filiais, onConcluido }) {
  const [editando, setEditando] = useState(null)
  return <div className="grid items-start gap-6 lg:grid-cols-[1fr_360px]">
    <div className="space-y-3">
      {filiais.map((f) => <article key={f.id} className="space-y-3 rounded-xl bg-panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 className="font-bold">{f.nome}</h2><p className="mt-1 text-sm text-slate-700">/{f.codigo_slug} · {f.ativa ? 'Ativa' : 'Inativa'}</p></div>
          <button onClick={() => setEditando(f)} className={SECUNDARIO} aria-label={`Editar unidade ${f.nome}`}>Editar unidade</button>
        </div>
        <p className="text-sm text-slate-700">Impressora: {f.ip_impressora || 'Não configurada'}</p>
        <div className="flex flex-wrap gap-2">
          {f.ativa && <a href={`/${f.codigo_slug}`} target="_blank" rel="noreferrer" className={SECUNDARIO}>Abrir formulário</a>}
          <Link to={`/gestao?unidade=${f.id}`} className={SECUNDARIO}>Gerenciar unidade</Link>
          <Link to={`/cozinha/${f.id}`} className={SECUNDARIO}>Painel da cozinha</Link>
          <Link to={`/entregas/${f.id}`} className={SECUNDARIO}>Entregas das copeiras</Link>
        </div>
      </article>)}
      {!filiais.length && <p className="rounded-xl bg-panel p-5">Cadastre a primeira unidade para começar.</p>}
    </div>
    <FormularioUnidade key={editando?.id || 'nova'} filial={editando} filiais={filiais}
      onCancelar={() => setEditando(null)} onConcluido={(m) => { setEditando(null); onConcluido(m) }} />
  </div>
}

function FormularioUnidade({ filial, filiais, onCancelar, onConcluido }) {
  const [form, setForm] = useState(() => ({ nome: filial?.nome || '', codigo_slug: filial?.codigo_slug || '', ativa: filial?.ativa ?? true,
    origem_filial_id: filiais.find((f) => f.ativa)?.id || filiais[0]?.id || '' }))
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState(null)
  const alterar = (chave, valor) => setForm((f) => ({ ...f, [chave]: valor }))

  async function salvar(e) {
    e.preventDefault()
    setSalvando(true); setErro(null)
    try {
      const dados = { nome: form.nome, codigo_slug: form.codigo_slug }
      if (filial) await api.patch(`/admin/filiais/${filial.id}`, { ...dados, ativa: form.ativa })
      else await api.post('/admin/filiais', { ...dados, origem_filial_id: Number(form.origem_filial_id) || null })
      if (!filial) setForm((f) => ({ ...f, nome: '', codigo_slug: '' }))
      onConcluido(filial ? 'Unidade atualizada.' : 'Unidade criada com formulários e dietas próprios.')
    } catch (e) { setErro(mensagemErro(e)) } finally { setSalvando(false) }
  }

  return <form onSubmit={salvar} className="space-y-4 rounded-xl bg-panel p-5">
    <h2 className="text-lg font-bold">{filial ? 'Editar unidade' : 'Nova unidade'}</h2>
    <Aviso erro={erro} />
    <Campo titulo="Nome da unidade"><input required maxLength={100} className={CAMPO} value={form.nome} onChange={(e) => alterar('nome', e.target.value)} /></Campo>
    <Campo titulo="Endereço do formulário"><input required maxLength={50} pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="Ex.: unidade-sul" className={CAMPO} value={form.codigo_slug}
      onChange={(e) => alterar('codigo_slug', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} /></Campo>
    {!filial && filiais.length > 0 && <><Campo titulo="Copiar configurações de"><select required className={CAMPO} value={form.origem_filial_id} onChange={(e) => alterar('origem_filial_id', e.target.value)}>
      {filiais.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}</select></Campo>
      <p className="text-xs text-slate-700">Copia formulários e dietas. A nova unidade poderá editar suas próprias opções.</p></>}
    {filial && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.ativa} onChange={(e) => alterar('ativa', e.target.checked)} />Unidade ativa</label>}
    <div className="flex flex-wrap gap-2"><button disabled={salvando} className={PRIMARIO}>{salvando ? 'Salvando…' : filial ? 'Salvar unidade' : 'Criar unidade'}</button>
      {filial && <button type="button" onClick={onCancelar} className={SECUNDARIO}>Cancelar</button>}</div>
  </form>
}

function Credenciais({ filiais, usuarios, usuarioAtual, onConcluido }) {
  const [editando, setEditando] = useState(null)
  return <div className="grid items-start gap-6 lg:grid-cols-[1fr_390px]">
    <div className="space-y-3">{usuarios.map((u) => <article key={u.id} className="rounded-xl bg-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-bold">{u.nome} {u.id === usuarioAtual.id && <span className="text-sm font-normal">(sua conta)</span>}</h2>
        <p className="mt-1 break-all text-sm text-slate-700">Usuário: <strong>{u.nome_usuario}</strong> · {PERFIS[u.perfil]} · {u.ativo ? 'Ativo' : 'Inativo'}</p></div>
        <button onClick={() => setEditando(u)} className={SECUNDARIO} aria-label={`Editar credencial ${u.nome}`}>Editar credencial</button></div>
      <p className="mt-3 text-sm text-slate-700">{u.perfil === 'ADMIN_TI' ? 'Acesso a todas as unidades' : u.filiais.map((f) => f.nome).join(', ') || 'Sem unidades vinculadas'}</p>
    </article>)}</div>
    <FormularioCredencial key={editando?.id || 'nova'} usuario={editando} usuarioAtual={usuarioAtual} filiais={filiais}
      onCancelar={() => setEditando(null)} onConcluido={(m) => { setEditando(null); onConcluido(m) }} />
  </div>
}

function FormularioCredencial({ usuario, usuarioAtual, filiais, onCancelar, onConcluido }) {
  const vazio = () => ({ nome: '', nome_usuario: '', senha: '', perfil: 'NUTRICIONISTA', ativo: true, filial_ids: [] })
  const [form, setForm] = useState(() => usuario ? { ...usuario, senha: '', filial_ids: usuario.filiais.map((f) => f.id) } : vazio())
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState(null)
  const propria = usuario?.id === usuarioAtual.id
  const alterar = (chave, valor) => setForm((f) => ({ ...f, [chave]: valor }))

  async function salvar(e) {
    e.preventDefault(); setErro(null)
    if (form.perfil !== 'ADMIN_TI' && !filiais.some((f) => f.ativa && form.filial_ids.includes(f.id))) {
      setErro('Selecione pelo menos uma unidade ativa para este usuário.'); return
    }
    setSalvando(true)
    try {
      const dados = { nome: form.nome, nome_usuario: form.nome_usuario, perfil: form.perfil, ativo: form.ativo, filial_ids: form.perfil === 'ADMIN_TI' ? [] : form.filial_ids }
      if (form.senha) dados.senha = form.senha
      if (usuario) await api.patch(`/admin/usuarios/${usuario.id}`, dados)
      else await api.post('/admin/usuarios', dados)
      if (!usuario) setForm(vazio())
      onConcluido(usuario ? 'Credencial atualizada.' : 'Credencial criada.')
    } catch (e) { setErro(mensagemErro(e)) } finally { setSalvando(false) }
  }

  return <form onSubmit={salvar} className="space-y-4 rounded-xl bg-panel p-5">
    <h2 className="text-lg font-bold">{usuario ? 'Editar credencial' : 'Nova credencial'}</h2>
    <Aviso erro={erro} />
    <Campo titulo="Nome"><input required maxLength={100} className={CAMPO} value={form.nome} onChange={(e) => alterar('nome', e.target.value)} /></Campo>
    <Campo titulo="Nome de usuário"><input required type="text" autoComplete="off" autoCapitalize="none" autoCorrect="off" spellCheck={false}
      minLength={3} maxLength={50} pattern={'[a-zA-Z0-9][a-zA-Z0-9._\\-]{2,49}'} placeholder="Ex.: maria.silva" aria-describedby="ajuda-nome-usuario"
      className={CAMPO} value={form.nome_usuario} onChange={(e) => alterar('nome_usuario', e.target.value.toLowerCase())} /></Campo>
    <p id="ajuda-nome-usuario" className="text-xs text-slate-700">De 3 a 50 caracteres, começando por letra ou número. Use letras sem acento, números, ponto, hífen ou sublinhado. Cada nome deve ser único.</p>
    <Campo titulo={usuario ? 'Nova senha (opcional)' : 'Senha'}><input required={!usuario} type="password" autoComplete="new-password" minLength={6} maxLength={72}
      placeholder={usuario ? 'Preencha para substituir a senha' : 'Mínimo de 6 caracteres'} className={CAMPO} value={form.senha} onChange={(e) => alterar('senha', e.target.value)} /></Campo>
    <Campo titulo="Perfil de acesso"><select disabled={propria} className={CAMPO} value={form.perfil} onChange={(e) => alterar('perfil', e.target.value)}>
      {Object.entries(PERFIS).map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}</select></Campo>
    {form.perfil === 'ADMIN_TI' ? <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">Acesso a todas as unidades e configurações do sistema.</p>
      : <fieldset className="space-y-2"><legend className="mb-2 text-sm font-medium">Unidades de acesso</legend>
        {filiais.map((f) => <label key={f.id} className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={form.filial_ids.includes(f.id)} disabled={!f.ativa && !form.filial_ids.includes(f.id)}
          onChange={(e) => alterar('filial_ids', e.target.checked ? [...form.filial_ids, f.id] : form.filial_ids.filter((id) => id !== f.id))} />{f.nome}{!f.ativa && ' (inativa)'}</label>)}
      </fieldset>}
    {usuario && <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={propria} checked={form.ativo} onChange={(e) => alterar('ativo', e.target.checked)} />Credencial ativa</label>}
    <div className="flex flex-wrap gap-2"><button disabled={salvando} className={PRIMARIO}>{salvando ? 'Salvando…' : usuario ? 'Salvar credencial' : 'Criar credencial'}</button>
      {usuario && <button type="button" onClick={onCancelar} className={SECUNDARIO}>Cancelar</button>}</div>
  </form>
}

function Impressoras({ filiais, onConcluido }) {
  const [filialId, setFilialId] = useState(filiais[0]?.id || '')
  const filial = filiais.find((f) => f.id === Number(filialId))
  return <div className="max-w-3xl space-y-4 rounded-xl bg-panel p-5">
    <h2 className="text-lg font-bold">Impressora padrão por unidade</h2>
    <Campo titulo="Unidade da impressora"><select className={CAMPO} value={filialId} onChange={(e) => setFilialId(e.target.value)}>
      {filiais.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}</select></Campo>
    {filial ? <FormularioImpressora key={filial.id} filial={filial} onConcluido={onConcluido} /> : <p>Cadastre uma unidade para adicionar sua impressora.</p>}
  </div>
}

function FormularioImpressora({ filial, onConcluido }) {
  const [ip, setIp] = useState(filial.ip_impressora || '')
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState(null)
  const [sucesso, setSucesso] = useState(null)

  async function salvar(e) {
    e.preventDefault(); setOcupado(true); setErro(null); setSucesso(null)
    try {
      const { data } = await api.patch(`/admin/filiais/${filial.id}/impressora`, { ip_impressora: ip.trim() || null })
      setIp(data.ip_impressora || ''); onConcluido('Configuração de impressora atualizada.')
    } catch (e) { setErro(mensagemErro(e)) } finally { setOcupado(false) }
  }

  async function testar() {
    setOcupado(true); setErro(null); setSucesso(null)
    try { const { data } = await api.post(`/admin/filiais/${filial.id}/impressora/testar`); setSucesso(data.mensagem) }
    catch (e) { setErro(mensagemErro(e)) } finally { setOcupado(false) }
  }

  return <form onSubmit={salvar} className="space-y-4">
    <Aviso erro={erro} sucesso={sucesso} />
    <Campo titulo="IP da impressora térmica"><input className={CAMPO} placeholder="Ex.: 10.1.140.50" value={ip} onChange={(e) => { setIp(e.target.value); setSucesso(null) }} /></Campo>
    <p className="text-sm text-slate-700">Impressora ESC/POS, conexão TCP na porta 9100. Deixe o IP vazio para remover a associação.</p>
    <div className="flex flex-wrap gap-2"><button disabled={ocupado} className={PRIMARIO}>{ocupado ? 'Aguarde…' : 'Salvar impressora'}</button>
      <button type="button" onClick={testar} disabled={ocupado || !filial.ip_impressora || ip.trim() !== filial.ip_impressora} className={SECUNDARIO}>Testar conexão</button></div>
    {ip.trim() !== (filial.ip_impressora || '') && <p className="text-xs text-slate-700">Salve o endereço antes de testar a conexão.</p>}
  </form>
}
