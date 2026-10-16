import { useEffect, useState } from 'react'
import { api } from '../services/api.js'

/** Painel do Administrador de TI: filiais, impressoras e utilizadores. */
export default function Admin() {
  const [aba, setAba] = useState('filiais')

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-slate-100">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">⚙️ Administração de TI</h1>
        <button onClick={() => { localStorage.clear(); window.location.href = '/login' }} className="rounded bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700">
          Sair
        </button>
      </header>

      <nav className="mb-6 flex gap-2">
        {[['filiais', '🏢 Filiais'], ['usuarios', '👥 Utilizadores']].map(([id, rotulo]) => (
          <button key={id} onClick={() => setAba(id)}
            className={`rounded-lg px-4 py-2 font-medium ${aba === id ? 'bg-blue-600' : 'bg-slate-800 hover:bg-slate-700'}`}>
            {rotulo}
          </button>
        ))}
      </nav>

      {aba === 'filiais' ? <AbaFiliais /> : <AbaUsuarios />}
    </div>
  )
}

function AbaFiliais() {
  const [filiais, setFiliais] = useState([])
  const [form, setForm] = useState({ nome: '', codigo_slug: '', ip_impressora: '' })

  const recarregar = () => api.get('/admin/filiais').then((r) => setFiliais(r.data))
  useEffect(() => { recarregar() }, [])

  async function criar(e) {
    e.preventDefault()
    try {
      await api.post('/admin/filiais', { ...form, ip_impressora: form.ip_impressora || null })
      setForm({ nome: '', codigo_slug: '', ip_impressora: '' })
      recarregar()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao criar filial')
    }
  }

  async function editarIp(f) {
    const ip = prompt(`IP da impressora térmica da unidade "${f.nome}":`, f.ip_impressora || '')
    if (ip === null) return
    await api.patch(`/admin/filiais/${f.id}`, { nome: f.nome, codigo_slug: f.codigo_slug, ip_impressora: ip || null })
    recarregar()
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_320px]">
      <div className="space-y-2">
        {filiais.map((f) => (
          <div key={f.id} className="flex items-center justify-between rounded-lg bg-slate-800 p-4">
            <div>
              <p className="font-medium">{f.nome}</p>
              <p className="text-sm text-slate-400">/{f.codigo_slug} · Impressora: {f.ip_impressora || 'não configurada'}</p>
            </div>
            <button onClick={() => editarIp(f)} className="rounded bg-slate-700 px-3 py-1 text-sm hover:bg-slate-600">🖨️ IP</button>
          </div>
        ))}
      </div>
      <form onSubmit={criar} className="h-fit space-y-3 rounded-xl bg-slate-800 p-4">
        <h3 className="font-bold">Nova filial</h3>
        <input required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })}
          placeholder="Nome (ex.: Unidade Sul)" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <input required value={form.codigo_slug} onChange={(e) => setForm({ ...form, codigo_slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') })}
          placeholder="Slug (ex.: unidade-sul)" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <input value={form.ip_impressora} onChange={(e) => setForm({ ...form, ip_impressora: e.target.value })}
          placeholder="IP da impressora (opcional)" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <button className="w-full rounded bg-blue-600 py-2 font-bold hover:bg-blue-500">Criar filial</button>
      </form>
    </div>
  )
}

function AbaUsuarios() {
  const [usuarios, setUsuarios] = useState([])
  const [form, setForm] = useState({ nome: '', email: '', senha: '', perfil: 'NUTRICIONISTA', filial_ids: [1] })

  const recarregar = () => api.get('/admin/usuarios').then((r) => setUsuarios(r.data))
  useEffect(() => { recarregar() }, [])

  async function criar(e) {
    e.preventDefault()
    try {
      await api.post('/admin/usuarios', form)
      setForm({ nome: '', email: '', senha: '', perfil: 'NUTRICIONISTA', filial_ids: [1] })
      recarregar()
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao criar utilizador')
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_320px]">
      <div className="space-y-2">
        {usuarios.map((u) => (
          <div key={u.id} className="flex items-center justify-between rounded-lg bg-slate-800 p-4">
            <div>
              <p className="font-medium">{u.nome} {!u.ativo && <span className="ml-1 rounded bg-slate-600 px-2 py-0.5 text-xs">INATIVO</span>}</p>
              <p className="text-sm text-slate-400">{u.email} · {u.perfil} · {u.filiais?.map((f) => f.nome).join(', ')}</p>
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={criar} className="h-fit space-y-3 rounded-xl bg-slate-800 p-4">
        <h3 className="font-bold">Novo utilizador</h3>
        <input required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })}
          placeholder="Nome" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="E-mail" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <input required type="password" minLength={6} value={form.senha} onChange={(e) => setForm({ ...form, senha: e.target.value })}
          placeholder="Palavra-passe (mín. 6)" className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2" />
        <select value={form.perfil} onChange={(e) => setForm({ ...form, perfil: e.target.value })}
          className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2">
          <option value="NUTRICIONISTA">Nutricionista (Gestor)</option>
          <option value="COZINHA">Cozinha (Operação)</option>
          <option value="ADMIN_TI">Administrador TI</option>
        </select>
        <button className="w-full rounded bg-blue-600 py-2 font-bold hover:bg-blue-500">Criar utilizador</button>
      </form>
    </div>
  )
}
