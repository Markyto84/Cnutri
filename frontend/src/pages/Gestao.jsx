import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../services/api.js'
import RefeicoesMedicas from '../components/RefeicoesMedicas.jsx'
import RelatorioEntregas from '../components/RelatorioEntregas.jsx'
import RelatorioDietas from '../components/RelatorioDietas.jsx'
import { SemUnidades } from '../context/AuthContext.jsx'
import { useAuth } from '../context/auth.js'

/** Painel da Nutrição: catálogo de dietas, editor de formulários e relatórios. */
export default function Gestao() {
  const [aba, setAba] = useState('dietas')
  const { usuario, sair } = useAuth()
  const [parametros, setParametros] = useSearchParams()
  const filiais = usuario.filiais || []
  const filial = filiais.find((f) => f.id === Number(parametros.get('unidade'))) || filiais[0]
  const filialId = filial?.id
  if (!filial) return <SemUnidades />

  return (
    <div className="min-h-screen bg-app-background p-6 text-slate-900">
      <header className="brand-header mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-brand">🥗 Gestão de Nutrição</h1>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={filialId}
            aria-label="Unidade de gestão"
            onChange={(e) => setParametros({ unidade: e.target.value })}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2"
          >
            {filiais.map((f) => (
              <option key={f.id} value={f.id}>{f.nome}</option>
            ))}
          </select>
          {usuario.perfil === 'ADMIN_TI' && <Link to="/admin" className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">Administração</Link>}
          <Link to={`/cozinha/${filialId}`} className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">Cozinha</Link>
          <Link to={`/entregas/${filialId}`} className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">Entregas</Link>
          <Link to="/senha" className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">Alterar minha senha</Link>
          <button onClick={sair} className="rounded bg-white px-4 py-2 text-sm hover:bg-slate-50">
            Sair
          </button>
        </div>
      </header>

      <nav className="mb-6 flex flex-wrap gap-2">
        {[['dietas', '📋 Dietas'], ['refeicoes-medicas', '🍽️ Refeições médicas'], ['formularios', '🧩 Formulários'], ['relatorios', '📊 Relatórios']].map(([id, rotulo]) => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`rounded-lg px-4 py-2 font-medium ${aba === id ? 'bg-brand text-white' : 'bg-white hover:bg-slate-50'}`}
          >
            {rotulo}
          </button>
        ))}
      </nav>

      {aba === 'dietas' && <AbaDietas key={filialId} filialId={filialId} />}
      {aba === 'refeicoes-medicas' && <RefeicoesMedicas key={filialId} filialId={filialId} />}
      {aba === 'formularios' && <AbaFormularios key={filialId} filialId={filialId} />}
      {aba === 'relatorios' && <AbaRelatorios key={filialId} filialId={filialId} />}
    </div>
  )
}

function AbaDietas({ filialId }) {
  const [dietas, setDietas] = useState([])
  const [nome, setNome] = useState('')
  const [severa, setSevera] = useState(false)
  const [editandoId, setEditandoId] = useState(null)
  const [rascunho, setRascunho] = useState({})

  const recarregar = () =>
    api.get('/gestao/dietas', { params: { filial_id: filialId } }).then((r) => setDietas(r.data))

  useEffect(() => { recarregar() }, [filialId])

  async function criar(e) {
    e.preventDefault()
    if (!nome.trim()) return
    await api.post('/gestao/dietas', { nome, severa }, { params: { filial_id: filialId } })
    setNome(''); setSevera(false)
    recarregar()
  }

  async function alternarAtiva(d) {
    if (d.ativa) await api.delete(`/gestao/dietas/${d.id}`)
    else await api.patch(`/gestao/dietas/${d.id}`, { nome: d.nome, severa: d.severa, descricao: d.descricao })
    recarregar()
  }

  function iniciarEdicao(d) {
    setEditandoId(d.id)
    setRascunho({ nome: d.nome, severa: d.severa, descricao: d.descricao || '' })
  }

  async function salvarEdicao(id) {
    await api.patch(`/gestao/dietas/${id}`, { ...rascunho, nome: rascunho.nome.trim() })
    setEditandoId(null)
    recarregar()
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_300px]">
      <div className="space-y-2">
        {dietas.map((d) => (
          <div key={d.id} className="rounded-lg bg-panel p-4">
            {editandoId === d.id ? (
              <div className="space-y-2">
                <input
                  value={rascunho.nome}
                  onChange={(e) => setRascunho({ ...rascunho, nome: e.target.value.toUpperCase() })}
                  className="w-full rounded border border-slate-300 bg-slate-50 px-3 py-2 font-medium uppercase"
                />
                <input
                  value={rascunho.descricao}
                  onChange={(e) => setRascunho({ ...rascunho, descricao: e.target.value })}
                  placeholder="Descrição (opcional)"
                  className="w-full rounded border border-slate-300 bg-slate-50 px-3 py-2 text-sm"
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!rascunho.severa} onChange={(e) => setRascunho({ ...rascunho, severa: e.target.checked })} />
                  Restrição severa (destaque vermelho no Kanban e na filipeta)
                </label>
                <div className="flex gap-2">
                  <button onClick={() => salvarEdicao(d.id)} className="rounded bg-brand px-4 py-1.5 text-sm font-bold hover:bg-brand-hover text-white">💾 Salvar</button>
                  <button onClick={() => setEditandoId(null)} className="rounded bg-slate-50 px-4 py-1.5 text-sm hover:bg-slate-200">Cancelar</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">
                    {d.nome} {d.severa && <span className="ml-1 rounded bg-red-600 px-2 py-0.5 text-xs text-white">SEVERA</span>}
                    {!d.ativa && <span className="ml-1 rounded bg-slate-200 px-2 py-0.5 text-xs">INATIVA</span>}
                  </p>
                  {d.descricao && <p className="text-sm text-slate-700">{d.descricao}</p>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => iniciarEdicao(d)} className="rounded bg-slate-50 px-3 py-1 text-sm hover:bg-slate-200" title="Editar nome, descrição e severidade">✏️ Editar</button>
                  <button onClick={() => alternarAtiva(d)} className="rounded bg-slate-50 px-3 py-1 text-sm hover:bg-slate-200">
                    {d.ativa ? 'Desativar' : 'Reativar'}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={criar} className="h-fit space-y-3 rounded-xl bg-panel p-4">
        <h3 className="font-bold">Nova dieta</h3>
        <p className="text-xs text-slate-700">Para editar uma dieta existente (nome, severidade…), use o botão ✏️ da lista.</p>
        <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome (ex.: Pastosa)"
          className="w-full rounded border border-slate-300 bg-slate-50 px-3 py-2" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={severa} onChange={(e) => setSevera(e.target.checked)} />
          Restrição severa (destaque vermelho)
        </label>
        <button className="w-full rounded bg-brand py-2 font-bold hover:bg-brand-hover text-white">Adicionar</button>
      </form>
    </div>
  )
}

// ── Utilitários de edição de listas (preservam Enter/linhas vazias durante a digitação) ──
const paraTexto = (v) => (Array.isArray(v) ? v.join('\n') : v ?? '')
const paraLista = (v) => paraTexto(v).split('\n').map((t) => t.trim()).filter(Boolean)
const temOpcoes = (campo) => ['selecao', 'radio'].includes(campo.tipo)

function normalizarParaEdicao(cfg) {
  return {
    ...cfg,
    campos: (cfg.campos || []).map((c) => {
      const base = { ...c }
      if (temOpcoes(c)) base.opcoes = paraTexto(c.opcoes)
      else delete base.opcoes
      if (c.tipo === 'cardapio')
        base.grupos = (c.grupos || []).map((g) => ({ ...g, dietas: paraTexto(g.dietas), opcoes: paraTexto(g.opcoes) }))
      else delete base.grupos
      return base
    }),
  }
}

function prepararTipo(campo, novoTipo) {
  const base = { ...campo, tipo: novoTipo }
  if (temOpcoes(base)) base.opcoes = paraTexto(campo.opcoes)
  else delete base.opcoes
  if (novoTipo === 'cardapio') {
    base.grupos = Array.isArray(campo.grupos) && campo.grupos.length
      ? campo.grupos.map((g) => ({ ...g, dietas: paraTexto(g.dietas), opcoes: paraTexto(g.opcoes) }))
      : [{ nome: 'Grupo 1', dietas: '', opcoes: '' }]
  } else delete base.grupos
  return base
}

function montarPayload(cfg) {
  return {
    ...cfg,
    campos: (cfg.campos || []).map((c) => {
      const base = { ...c }
      if (temOpcoes(c)) base.opcoes = paraLista(c.opcoes)
      else delete base.opcoes
      if (c.tipo === 'cardapio')
        base.grupos = (c.grupos || []).map((g) => ({ ...g, dietas: paraLista(g.dietas), opcoes: paraLista(g.opcoes) }))
      else delete base.grupos
      return base
    }),
  }
}

function AbaFormularios({ filialId }) {
  const [tipo, setTipo] = useState('ENFERMAGEM')
  const [config, setConfig] = useState(null)

  const recarregar = (t = tipo) =>
    api.get(`/gestao/formularios/${filialId}/${t}`).then((r) =>
      setConfig({
        ...normalizarParaEdicao(r.data?.esquema_json || { titulo: '', cabecalho: '', campos: [] }),
        versao: r.data?.atualizado_em || null, // para proteção contra edição concorrente
      })
    )

  useEffect(() => { recarregar(tipo) }, [filialId, tipo])

  function editarCampo(idx, campo) {
    setConfig((c) => ({ ...c, campos: c.campos.map((x, i) => (i === idx ? campo : x)) }))
  }

  function adicionarCampo() {
    setConfig((c) => ({ ...c, campos: [...c.campos, { id: `campo_${Date.now()}`, rotulo: 'Novo campo', tipo: 'texto', obrigatorio: false }] }))
  }

  function removerCampo(idx) {
    setConfig((c) => ({ ...c, campos: c.campos.filter((_, i) => i !== idx) }))
  }

  async function salvar() {
    const { versao, ...esquema } = config
    try {
      await api.put(`/gestao/formularios/${filialId}/${tipo}`, { esquema_json: montarPayload(esquema), versao })
      alert('Formulário publicado! Atualização instantânea nos quiosques ✅')
      recarregar(tipo)
    } catch (e) {
      alert(e.response?.data?.detail || 'Erro ao guardar')
    }
  }

  async function resetar() {
    await api.post(`/gestao/formularios/${filialId}/${tipo}/resetar`)
    recarregar()
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        {['ENFERMAGEM', 'MEDICO'].map((t) => (
          <button key={t} onClick={() => setTipo(t)} className={`rounded px-4 py-2 text-sm ${tipo === t ? 'bg-brand text-white' : 'bg-white hover:bg-slate-50'}`}>
            {t === 'ENFERMAGEM' ? 'Enfermagem / Paciente' : 'Médico'}
          </button>
        ))}
      </div>

      {config && (
        <div className="max-w-3xl space-y-3">
          <label className="block text-sm font-medium">
            <span className="mb-1 block">Título do formulário</span>
            <input
              value={config.titulo || ''}
              onChange={(e) => setConfig({ ...config, titulo: e.target.value })}
              placeholder="Título do formulário"
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 font-bold"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Texto informativo exibido no topo do quiosque</span>
            <textarea
              rows={6}
              value={config.cabecalho || ''}
              onChange={(e) => setConfig({ ...config, cabecalho: e.target.value })}
              placeholder="Horários, orientações e avisos que aparecem antes dos campos..."
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm"
            />
          </label>
          {config.campos.map((campo, i) => (
            <fieldset key={campo.id} className="min-w-0 rounded-lg border border-slate-300 bg-panel p-3">
              <legend className="break-words px-1 text-sm font-semibold text-brand-ink">{campo.rotulo.trim() || 'Novo campo'}</legend>
              <div className="grid grid-cols-2 items-end gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,180px)_auto_auto]">
                <label className="col-span-2 min-w-0 text-sm md:col-span-1">
                  <span className="mb-1 block font-medium">Nome do campo</span>
                  <input value={campo.rotulo} onChange={(e) => editarCampo(i, { ...campo, rotulo: e.target.value })}
                    className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1" />
                </label>
                <label className="col-span-2 min-w-0 text-sm md:col-span-1">
                  <span className="mb-1 block font-medium">Tipo do campo</span>
                  <select value={campo.tipo} onChange={(e) => editarCampo(i, prepararTipo(campo, e.target.value))}
                    className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1 text-sm">
                    <option value="texto">Texto</option>
                    <option value="texto_longo">Texto longo</option>
                    <option value="data">Data</option>
                    <option value="selecao">Lista de opções</option>
                    <option value="radio">Botões de seleção única</option>
                    <option value="cardapio">Cardápio (depende da dieta)</option>
                    <option value="selecao_dietas">Seleção de dietas</option>
                  </select>
                </label>
                <label className="flex items-center gap-1 py-1 text-xs">
                  <input type="checkbox" checked={!!campo.obrigatorio} onChange={(e) => editarCampo(i, { ...campo, obrigatorio: e.target.checked })} />
                  Obrigatório
                </label>
                <button onClick={() => removerCampo(i)} aria-label={`Remover campo ${campo.rotulo}`} className="justify-self-end py-1 text-red-700 hover:text-red-800">✕</button>
              </div>
            </fieldset>
          ))}
          {tipo === 'ENFERMAGEM' && config.campos.some((c) => c.id === 'para') && config.campos.some((c) => c.id === 'cardapio' && c.tipo === 'cardapio') && (
            <p className="rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">
              Para acompanhantes, a dieta é sempre GERAL. Em “Paciente e Acompanhante”, o campo
              “Cardápio do acompanhante” aparece automaticamente e usa as opções do grupo que
              contém GERAL abaixo. Ao alterar esse grupo, os dois campos recebem a atualização.
            </p>
          )}
          {config.campos.some((c) => c.tipo === 'cardapio') && config.campos.map((c, i) =>
            c.tipo === 'cardapio' ? (
              <div key={`card-${c.id}`} className="space-y-3 rounded bg-panel p-3 text-sm">
                <h3 className="font-semibold text-brand-ink">{c.rotulo.trim() || 'Novo campo'}</h3>
                <p className="text-slate-700">Cada grupo lista as dietas que o ativam e as opções de cardápio correspondentes:</p>
                {(c.grupos || []).map((g, gi) => (
                  <div key={gi} className="space-y-2 rounded border border-slate-300 p-3">
                    <div className="flex items-end gap-2">
                      <label className="min-w-0 flex-1">
                        <span className="mb-1 block font-medium">Nome do grupo</span>
                        <input
                          value={g.nome || ''}
                          onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, nome: e.target.value } : x)) })}
                          placeholder="Nome do grupo (ex.: Grupo 1)"
                          className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1"
                        />
                      </label>
                      <button
                        onClick={() => editarCampo(i, { ...c, grupos: c.grupos.filter((_, xi) => xi !== gi) })}
                        aria-label={`Remover grupo ${g.nome || gi + 1} de ${c.rotulo}`}
                        className="py-1 text-red-700 hover:text-red-800"
                      >✕</button>
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      <label className="block">
                        <span className="mb-1 block text-xs text-slate-700">Tipos de dieta que ativam este grupo (uma por linha, nome exato):</span>
                        <textarea
                          rows={4}
                          className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1"
                          value={paraTexto(g.dietas)}
                          onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, dietas: e.target.value } : x)) })}
                        />
                      </label>
                      <label className="block">
                        <span className="mb-1 block text-xs text-slate-700">Opções de cardápio deste grupo (uma por linha):</span>
                        <textarea
                          rows={4}
                          className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1"
                          value={paraTexto(g.opcoes)}
                          onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, opcoes: e.target.value } : x)) })}
                        />
                      </label>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => editarCampo(i, { ...c, grupos: [...(c.grupos || []), { nome: `Grupo ${(c.grupos || []).length + 1}`, dietas: '', opcoes: '' }] })}
                  className="rounded bg-slate-50 px-3 py-1 text-xs hover:bg-slate-200"
                >+ Adicionar grupo</button>
              </div>
            ) : null
          )}
          {config.campos.some(temOpcoes) && (
            <div className="space-y-4 rounded bg-panel p-3 text-sm">
              <p className="text-slate-700">Opções das listas (uma por linha):</p>
              {config.campos.map((c, i) =>
                temOpcoes(c) ? (
                  <label key={c.id} className="block">
                    <span className="mb-1 block break-words font-semibold text-brand-ink">{c.rotulo.trim() || 'Novo campo'}</span>
                    <textarea
                      rows={4}
                      className="w-full rounded border border-slate-300 bg-slate-50 px-2 py-1"
                      value={paraTexto(c.opcoes)}
                      onChange={(e) => editarCampo(i, { ...c, opcoes: e.target.value })}
                    />
                  </label>
                ) : null
              )}
            </div>
          )}
          <div className="flex flex-wrap gap-2 pt-2">
            <button onClick={adicionarCampo} className="rounded bg-slate-50 px-4 py-2 text-sm hover:bg-slate-200">+ Adicionar campo</button>
            <button onClick={resetar} className="rounded bg-slate-50 px-4 py-2 text-sm hover:bg-slate-200">↺ Restaurar padrão</button>
            <button onClick={salvar} className="rounded bg-brand px-6 py-2 font-bold hover:bg-brand-hover text-white">💾 Publicar</button>
          </div>
        </div>
      )}
    </div>
  )
}

function AbaRelatorios({ filialId }) {
  const [sla, setSla] = useState(null)
  const [consumo, setConsumo] = useState([])
  const [dietas, setDietas] = useState([])

  useEffect(() => {
    api.get('/relatorios/sla', { params: { filial_id: filialId } }).then((r) => setSla(r.data))
    api.get('/relatorios/consumo-medico', { params: { filial_id: filialId } }).then((r) => setConsumo(r.data))
    api.get('/relatorios/dietas', { params: { filial_id: filialId } }).then((r) => setDietas(r.data))
  }, [filialId])

  return (
    <div className="grid gap-6 md:grid-cols-3">
      <RelatorioDietas filialId={filialId} />
      <div className="rounded-xl bg-panel p-5">
        <h3 className="mb-3 font-bold text-brand">⏱️ SLA da Cozinha</h3>
        {sla && (
          <>
            <p className="text-4xl font-bold text-slate-900">{sla.sla_medio_minutos ?? '—'}<span className="text-lg text-slate-700"> min</span></p>
            <p className="mt-1 text-sm text-slate-700">{sla.total_concluidos} pedidos concluídos</p>
          </>
        )}
      </div>

      <div className="rounded-xl bg-panel p-5">
        <h3 className="mb-3 font-bold text-amber-900">👨‍⚕️ Consumo — Corpo Médico</h3>
        {consumo.length === 0 && <p className="text-sm text-slate-700">Sem registos ainda.</p>}
        <ul className="space-y-1 text-sm">
          {consumo.map((c, i) => (
            <li key={i} className="flex justify-between">
              <span>{c.solicitante} <span className="text-slate-700">({c.turno})</span></span>
              <span className="font-bold">{c.total}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl bg-panel p-5">
        <h3 className="mb-3 font-bold text-brand">🥣 Volume por Dieta</h3>
        {dietas.length === 0 && <p className="text-sm text-slate-700">Sem registos ainda.</p>}
        <ul className="space-y-1 text-sm">
          {dietas.map((d, i) => (
            <li key={i} className="flex justify-between">
              <span>{d.dieta}</span>
              <span className="font-bold">{d.total}</span>
            </li>
          ))}
        </ul>
      </div>
      <RelatorioEntregas filialId={filialId} />
    </div>
  )
}
