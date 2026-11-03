import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '../services/api.js'
import { AuthContext, inicioDoUsuario, useAuth } from './auth.js'
import { limparRetirada } from '../services/retiradaEntrega.js'
import { limparCodigoRecebimento } from '../services/recebimentoQr.js'

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [plantaoOnline, setPlantaoOnline] = useState(false)
  const [carregando, setCarregando] = useState(() => Boolean(localStorage.getItem('token')))

  useEffect(() => {
    const tokenInicial = localStorage.getItem('token')
    if (!tokenInicial) return
    const controller = new AbortController()
    api.get('/auth/me', { signal: controller.signal, ignorarRedirecionamento401: true })
      .then(({ data }) => { if (!controller.signal.aborted && localStorage.getItem('token') === tokenInicial) setUsuario(data) })
      .catch(() => { if (!controller.signal.aborted && (!localStorage.getItem('token') || localStorage.getItem('token') === tokenInicial)) setUsuario(null) })
      .finally(() => { if (!controller.signal.aborted && (!localStorage.getItem('token') || localStorage.getItem('token') === tokenInicial)) setCarregando(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    function sincronizar(evento) {
      if (evento.key !== 'token') return
      setUsuario(null)
      setCarregando(Boolean(evento.newValue))
      if (!evento.newValue) return
      const token = evento.newValue
      api.get('/auth/me', { ignorarRedirecionamento401: true })
        .then(({ data }) => { if (localStorage.getItem('token') === token) setUsuario(data) })
        .catch(() => { if (!localStorage.getItem('token') || localStorage.getItem('token') === token) setUsuario(null) })
        .finally(() => { if (!localStorage.getItem('token') || localStorage.getItem('token') === token) setCarregando(false) })
    }
    window.addEventListener('storage', sincronizar)
    return () => window.removeEventListener('storage', sincronizar)
  }, [])

  function entrar(dados) {
    localStorage.setItem('token', dados.access_token)
    localStorage.setItem('perfil', dados.perfil)
    localStorage.setItem('nome', dados.nome)
    const sessao = { id: dados.usuario_id, nome: dados.nome, perfil: dados.perfil, filiais: dados.filiais, troca_senha_obrigatoria: Boolean(dados.troca_senha_obrigatoria), origem_autenticacao: dados.origem_autenticacao || 'LOCAL' }
    setUsuario(sessao)
    setPlantaoOnline(false)
    setCarregando(false)
    return sessao
  }

  function sair() {
    limparRetirada()
    limparCodigoRecebimento()
    const token = localStorage.getItem('token')
    const encerramento = token ? api.post('/auth/logout', {}, {
      headers: { Authorization: `Bearer ${token}` }, ignorarRedirecionamento401: true,
    }).catch(() => {}) : Promise.resolve()
    for (const chave of ['token', 'perfil', 'nome']) localStorage.removeItem(chave)
    setUsuario(null)
    setPlantaoOnline(false)
    setCarregando(false)
    return encerramento
  }

  async function atualizarUsuario() {
    const tokenAtual = localStorage.getItem('token')
    const { data } = await api.get('/auth/me')
    if (tokenAtual && localStorage.getItem('token') === tokenAtual) setUsuario(data)
    return data
  }

  return <AuthContext.Provider value={{ usuario, carregando, entrar, sair, atualizarUsuario, plantaoOnline }}>{children}</AuthContext.Provider>
}

export function RotaProtegida({ perfis, permitirTrocaSenha = false, children }) {
  const { usuario, carregando } = useAuth()
  if (carregando) return <div className="flex min-h-screen items-center justify-center bg-app-background text-slate-950">Carregando acesso…</div>
  if (!usuario) return <Navigate to="/login" replace />
  if (usuario.troca_senha_obrigatoria && !permitirTrocaSenha) return <Navigate to="/senha" replace />
  if (perfis && !perfis.includes(usuario.perfil)) return <Navigate to={inicioDoUsuario(usuario)} replace />
  return children
}

export function SemUnidades() {
  const { sair } = useAuth()
  return <div className="flex min-h-screen items-center justify-center bg-app-background p-6">
    <div className="max-w-lg space-y-4 rounded-xl bg-panel p-6 text-slate-900">
      <h1 className="text-xl font-bold">Nenhuma unidade disponível</h1>
      <p>Seu usuário ainda não possui acesso a uma unidade ativa. Solicite o vínculo ao administrador.</p>
      <button onClick={sair} className="rounded bg-slate-50 px-4 py-2">Sair</button>
    </div>
  </div>
}
