import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../services/api.js'
import { destinoAposLogin, useAuth } from '../context/auth.js'
import { Icone, IlustracaoCuidado, MarcaAplicacao } from '../components/Identidade.jsx'

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
      navegar(destinoAposLogin(sessao, parametros), { replace: true })
    } catch (err) {
      setErro(err.response?.data?.detail || 'Falha no login')
    } finally {
      setCarregando(false)
    }
  }

  return (
    <main className="auth-shell">
      <div className="auth-layout">
        <aside className="auth-story"><MarcaAplicacao /><IlustracaoCuidado />
          <p className="eyebrow">Pessoas no centro do cuidado</p><h2>Nutrir também<br />é cuidar.</h2>
          <p>Uma rotina mais simples para quem solicita, prepara e entrega cada refeição.</p>
        </aside>
        <section className="auth-form-panel" aria-labelledby="titulo-login">
          <MarcaAplicacao /><p className="eyebrow">Seu espaço de trabalho</p>
          <h1 id="titulo-login">Que bom ter você aqui.</h1><p className="mt-3 text-sm text-slate-700">Acesse sua conta para continuar.</p>
      <form onSubmit={submeter} className="space-y-5">

        {erro && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{erro}</div>}

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
          className="ui-button ui-button-primary w-full"
        >
          {carregando ? 'Entrando…' : <><span>Entrar</span><Icone nome="seta" tamanho={18} /></>}
        </button>

      </form>
          <p className="auth-help"><Icone nome="chave" tamanho={18} /><span>Use o usuário fornecido pela TI. Para contas da rede, utilize sua senha do AD. Se precisar de ajuda, procure o suporte da sua unidade.</span></p>
        </section>
      </div>
    </main>
  )
}
