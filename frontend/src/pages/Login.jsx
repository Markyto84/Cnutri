import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api.js'

export default function Login() {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const navegar = useNavigate()

  async function submeter(e) {
    e.preventDefault()
    setCarregando(true)
    setErro(null)
    try {
      const dados = new URLSearchParams({ username: email, password: senha })
      const r = await api.post('/auth/login', dados)
      localStorage.setItem('token', r.data.access_token)
      localStorage.setItem('perfil', r.data.perfil)
      localStorage.setItem('nome', r.data.nome)
      navegar(r.data.perfil === 'COZINHA' ? '/cozinha/1' : '/gestao')
    } catch (err) {
      setErro(err.response?.data?.detail || 'Falha no login')
    } finally {
      setCarregando(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-app-background p-4">
      <form onSubmit={submeter} className="w-full max-w-sm space-y-4 rounded-2xl bg-panel p-8 shadow-xl">
        <h1 className="text-center text-2xl font-bold text-slate-900">🏥 Dietas Hospitalares</h1>
        <p className="text-center text-sm text-slate-700">Acesso administrativo e de produção</p>

        {erro && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</div>}

        <input
          type="email"
          placeholder="E-mail ou matrícula"
          className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-blue-600"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Palavra-passe"
          className="w-full rounded-lg border border-slate-300 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-blue-600"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={carregando}
          className="w-full rounded-lg bg-blue-600 py-3 font-bold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {carregando ? 'A entrar…' : 'Entrar'}
        </button>

        <p className="text-center text-xs text-slate-700">
          Demo: admin@hospital.local / Trocar&#64;123
        </p>
      </form>
    </div>
  )
}
