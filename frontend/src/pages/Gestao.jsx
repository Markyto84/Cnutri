import { useEffect, useState } from 'react'
import { api } from '../services/api.js'

/** Painel da Nutrição: catálogo de dietas, editor de formulários e relatórios. */
export default function Gestao() {
  const [aba, setAba] = useState('dietas')
  const [filialId, setFilialId] = useState(1)
  const [filiais, setFiliais] = useState([])
  const perfil = localStorage.getItem('perfil')

  useEffect(() => {
    // Para a demo, lista pública de filiais via config do kiosk não existe;
    // usamos a filial 1 (seed) e, para ADMIN, a lista completa.
    if (perfil === 'ADMIN_TI') {
      api.get('/admin/filiais').then((r) => setFiliais(r.data)).catch(() => {})
    } else {
      setFiliais([{ id: 1, nome: 'Centro Médico Prevent Senior Havaí' }])
    }
  }, [perfil])

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">🥗 Gestão de Nutrição</h1>
        <div className="flex items-center gap-3">
          <select
            value={filialId}
            onChange={(e) => setFilialId(Number(e.target.value))}
            className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2"
          >
            {filiais.map((f) => (
              <option key={f.id} value={f.id}>{f.nome}</option>
            ))}
          </select>
          <button onClick={() => { localStorage.clear(); window.location.href = '/login' }} className="rounded bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700">
            Sair
          </button>
        </div>
      </header>

      <nav className="mb-6 flex gap-2">
        {[['dietas', '📋 Dietas'], ['formularios', '🧩 Formulários'], ['relatorios', '📊 Relatórios']].map(([id, rotulo]) => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`rounded-lg px-4 py-2 font-medium ${aba === id ? 'bg-blue-600' : 'bg-slate-800 hover:bg-slate-700'}`}
          >
            {rotulo}
          </button>
        ))}
      </nav>

      {aba === 'dietas' && <AbaDietas filialId={filialId} />}
      {aba === 'formularios' && <AbaFormularios filialId={filialId} />}
      {aba === 'relatorios' && <AbaRelatorios filialId={filialId} />}
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
          <div key={d.id} className="rounded-lg bg-slate-800 p-4">
            {editandoId === d.id ? (
              <div className="space-y-2">
                <input
                  value={rascunho.nome}
                  onChange={(e) => setRascunho({ ...rascunho, nome: e.target.value.toUpperCase() })}
                  className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 font-medium uppercase"
                />
                <input
                  value={rascunho.descricao}
                  onChange={(e) => setRascunho({ ...rascunho, descricao: e.target.value })}
                  placeholder="Descrição (opcional)"
                  className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-sm"
                />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!rascunho.severa} onChange={(e) => setRascunho({ ...rascunho, severa: e.target.checked })} />
                  Restrição severa (destaque vermelho no Kanban e na filipeta)
                </label>
                <div className="flex gap-2">
                  <button onClick={() => salvarEdicao(d.id)} className="rounded bg-blue-600 px-4 py-1.5 text-sm font-bold hover:bg-blue-500">💾 Salvar</button>
                  <button onClick={() => setEditandoId(null)} className="rounded bg-slate-700 px-4 py-1.5 text-sm hover:bg-slate-600">Cancelar</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">
                    {d.nome} {d.severa && <span className="ml-1 rounded bg-red-600 px-2 py-0.5 text-xs">SEVERA</span>}
                    {!d.ativa && <span className="ml-1 rounded bg-slate-600 px-2 py-0.5 text-xs">INATIVA</span>}
                  </p>
                  {d.descricao && <p className="text-sm text-slate-400">{d.descricao}</p>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => iniciarEdicao(d)} className="rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600" title="Editar nome, descrição e severidade">✏️ Editar</button>
                  <button onClick={() => alternarAtiva(d)} className="rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600">
                    {d.ativa ? 'Desativar' : 'Reativar'}
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={criar} className="h-fit space-y-3 rounded-xl bg-slate-800 p-4">
        <h3 className="font-bold">Nova dieta</h3>
        <p className="text-xs text-slate-400">Para editar uma dieta existente (nome, severidade…), use o botão ✏️ da lista.</p>
        <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome (ex.: Pastosa)"
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={severa} onChange={(e) => setSevera(e.target.checked)} />
          Restrição severa (destaque vermelho)
        </label>
        <button className="w-full rounded bg-blue-600 py-2 font-bold hover:bg-blue-500">Adicionar</button>
      </form>
    </div>
  )
}

// ── Utilitários de edição de listas (preservam Enter/linhas vazias durante a digitação) ──
const paraTexto = (v) => (Array.isArray(v) ? v.join('\n') : v ?? '')
const paraLista = (v) => paraTexto(v).split('\n').map((t) => t.trim()).filter(Boolean)

function normalizarParaEdicao(cfg) {
  return {
    ...cfg,
    campos: (cfg.campos || []).map((c) => {
      const base = { ...c }
      if (c.tipo === 'selecao') base.opcoes = paraTexto(c.opcoes)
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
  if (novoTipo === 'selecao') base.opcoes = paraTexto(campo.opcoes)
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
      if (c.tipo === 'selecao') base.opcoes = paraLista(c.opcoes)
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
      <div className="mb-4 flex gap-2">
        {['ENFERMAGEM', 'MEDICO'].map((t) => (
          <button key={t} onClick={() => setTipo(t)} className={`rounded px-4 py-2 text-sm ${tipo === t ? 'bg-emerald-600' : 'bg-slate-800 hover:bg-slate-700'}`}>
            {t === 'ENFERMAGEM' ? 'Enfermagem / Paciente' : 'Médico'}
          </button>
        ))}
      </div>

      {config && (
        <div className="max-w-3xl space-y-3">
          <input
            value={config.titulo || ''}
            onChange={(e) => setConfig({ ...config, titulo: e.target.value })}
            placeholder="Título do formulário"
            className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 font-bold"
          />
          <div>
            <label className="mb-1 block text-sm text-slate-300">Texto informativo exibido no topo do quiosque</label>
            <textarea
              rows={6}
              value={config.cabecalho || ''}
              onChange={(e) => setConfig({ ...config, cabecalho: e.target.value })}
              placeholder="Horários, orientações e avisos que aparecem antes dos campos..."
              className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm"
            />
          </div>
          {config.campos.map((campo, i) => (
            <div key={i} className="grid grid-cols-[1fr_130px_90px_40px] items-center gap-2 rounded bg-slate-800 p-3">
              <input value={campo.rotulo} onChange={(e) => editarCampo(i, { ...campo, rotulo: e.target.value })}
                className="rounded border border-slate-600 bg-slate-700 px-2 py-1" />
              <select value={campo.tipo} onChange={(e) => editarCampo(i, prepararTipo(campo, e.target.value))}
                className="rounded border border-slate-600 bg-slate-700 px-2 py-1 text-sm">
                <option value="texto">Texto</option>
                <option value="texto_longo">Texto longo</option>
                <option value="data">Data</option>
                <option value="selecao">Lista de opções</option>
                <option value="cardapio">Cardápio (depende da dieta)</option>
                <option value="selecao_dietas">Seleção de dietas</option>
              </select>
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={!!campo.obrigatorio} onChange={(e) => editarCampo(i, { ...campo, obrigatorio: e.target.checked })} />
                Obrig.
              </label>
              <button onClick={() => removerCampo(i)} className="text-red-400 hover:text-red-300">✕</button>
            </div>
          ))}
          {config.campos.some((c) => c.tipo === 'cardapio') && config.campos.map((c, i) =>
            c.tipo === 'cardapio' ? (
              <div key={`card-${i}`} className="rounded bg-slate-800 p-3 text-sm space-y-3">
                <p className="font-medium text-slate-300">Grupos do campo “{c.rotulo}” — cada grupo lista as dietas que o ativam e as opções de cardápio correspondentes:</p>
                {(c.grupos || []).map((g, gi) => (
                  <div key={gi} className="space-y-2 rounded border border-slate-600 p-3">
                    <div className="flex items-center gap-2">
                      <input
                        value={g.nome || ''}
                        onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, nome: e.target.value } : x)) })}
                        placeholder="Nome do grupo (ex.: Grupo 1)"
                        className="flex-1 rounded border border-slate-600 bg-slate-700 px-2 py-1"
                      />
                      <button
                        onClick={() => editarCampo(i, { ...c, grupos: c.grupos.filter((_, xi) => xi !== gi) })}
                        className="text-red-400 hover:text-red-300"
                      >✕</button>
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      <div>
                        <label className="mb-1 block text-xs text-slate-400">Tipos de dieta que ativam este grupo (uma por linha, nome exato):</label>
                        <textarea
                          rows={4}
                          className="w-full rounded border border-slate-600 bg-slate-700 px-2 py-1"
                          value={paraTexto(g.dietas)}
                          onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, dietas: e.target.value } : x)) })}
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs text-slate-400">Opções de cardápio deste grupo (uma por linha):</label>
                        <textarea
                          rows={4}
                          className="w-full rounded border border-slate-600 bg-slate-700 px-2 py-1"
                          value={paraTexto(g.opcoes)}
                          onChange={(e) => editarCampo(i, { ...c, grupos: c.grupos.map((x, xi) => (xi === gi ? { ...x, opcoes: e.target.value } : x)) })}
                        />
                      </div>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => editarCampo(i, { ...c, grupos: [...(c.grupos || []), { nome: `Grupo ${(c.grupos || []).length + 1}`, dietas: '', opcoes: '' }] })}
                  className="rounded bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
                >+ Adicionar grupo</button>
              </div>
            ) : null
          )}
          {config.campos.some((c) => c.tipo === 'selecao') && (
            <div className="rounded bg-slate-800 p-3 text-sm">
              <p className="mb-1 text-slate-300">Opções das listas (uma por linha):</p>
              {config.campos.map((c, i) =>
                c.tipo === 'selecao' ? (
                  <textarea
                    key={i}
                    rows={4}
                    className="mt-1 w-full rounded border border-slate-600 bg-slate-700 px-2 py-1"
                    value={paraTexto(c.opcoes)}
                    onChange={(e) => editarCampo(i, { ...c, opcoes: e.target.value })}
                  />
                ) : null
              )}
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <button onClick={adicionarCampo} className="rounded bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600">+ Adicionar campo</button>
            <button onClick={resetar} className="rounded bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600">↺ Restaurar padrão</button>
            <button onClick={salvar} className="rounded bg-blue-600 px-6 py-2 font-bold hover:bg-blue-500">💾 Publicar</button>
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
      <div className="rounded-xl bg-slate-800 p-5">
        <h3 className="mb-3 font-bold text-blue-400">⏱️ SLA da Cozinha</h3>
        {sla && (
          <>
            <p className="text-4xl font-bold text-white">{sla.sla_medio_minutos ?? '—'}<span className="text-lg text-slate-400"> min</span></p>
            <p className="mt-1 text-sm text-slate-400">{sla.total_concluidos} pedidos concluídos</p>
          </>
        )}
      </div>

      <div className="rounded-xl bg-slate-800 p-5">
        <h3 className="mb-3 font-bold text-amber-400">👨‍⚕️ Consumo — Corpo Médico</h3>
        {consumo.length === 0 && <p className="text-sm text-slate-400">Sem registos ainda.</p>}
        <ul className="space-y-1 text-sm">
          {consumo.map((c, i) => (
            <li key={i} className="flex justify-between">
              <span>{c.solicitante} <span className="text-slate-500">({c.turno})</span></span>
              <span className="font-bold">{c.total}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl bg-slate-800 p-5">
        <h3 className="mb-3 font-bold text-emerald-400">🥣 Volume por Dieta</h3>
        {dietas.length === 0 && <p className="text-sm text-slate-400">Sem registos ainda.</p>}
        <ul className="space-y-1 text-sm">
          {dietas.map((d, i) => (
            <li key={i} className="flex justify-between">
              <span>{d.dieta}</span>
              <span className="font-bold">{d.total}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
