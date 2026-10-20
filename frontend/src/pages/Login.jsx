import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../services/api.js'
import { inicioDoUsuario, useAuth } from '../context/auth.js'

export default function Login() {
  const [nomeUsuario, setNomeUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const { entrar } = useAuth()

  async function submeter(e) {
    e.preventDefault()
    setCarregando(true)
    setErro(null)
    try {
      const dados = new URLSearchParams({ username: nomeUsuario.trim(), password: senha })
      const r = await api.post('/auth/login', dados)
      const sessao = entrar(r.data)
      const unidade = Number(parametros.get('unidade'))
      const destino = sessao.perfil === 'COPEIRA' && sessao.filiais.some((f) => f.id === unidade && f.ativa)
        ? `/entregas/${unidade}` : inicioDoUsuario(sessao)
      navegar(destino, { replace: true })
    } catch (err) {
      setErro(err.response?.data?.detail || 'Falha no login')
    } finally {
      setCarregando(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-app-background p-4">
      <form onSubmit={submeter} className="w-full max-w-sm space-y-4 rounded-2xl border-t-4 border-brand-vibrant bg-panel p-8 shadow-xl">
        <h1 className="text-center text-2xl font-bold text-brand">🏥 Dietas Hospitalares</h1>
        <p className="text-center text-sm text-slate-700">Gestão e entrada das copeiras no plantão</p>

        {erro && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</div>}

        <label className="block text-sm font-medium text-slate-900">Usuário
        <input
          type="text"
          name="username"
          placeholder="Nome de usuário"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={50}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
          value={nomeUsuario}
          onChange={(e) => setNomeUsuario(e.target.value)}
          required
        /></label>
        <label className="block text-sm font-medium text-slate-900">Senha
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          placeholder="Senha"
          className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-brand"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
        /></label>
        <button
          type="submit"
          disabled={carregando}
          className="w-full rounded-lg bg-brand py-3 font-bold text-white hover:bg-brand-hover disabled:opacity-50"
        >
          {carregando ? 'A entrar…' : 'Entrar'}
        </button>

        <p className="text-center text-xs text-slate-700">
          Use o usuário e a senha fornecidos pelo administrador de TI.
        </p>
      </form>
    </div>
  )
}
