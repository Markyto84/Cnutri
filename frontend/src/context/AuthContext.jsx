import { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api } from '../services/api.js'
import { AuthContext, inicioDoUsuario, useAuth } from './auth.js'

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [plantaoOnline, setPlantaoOnline] = useState(false)
  const { pathname } = useLocation()
  const unidadeNaPagina = pathname.match(/^\/(?:entregas|cozinha)\/(\d+)/)?.[1]
  const filialPresenca = unidadeNaPagina
    ? usuario?.filiais?.find((f) => f.id === Number(unidadeNaPagina) && f.ativa)?.id
    : usuario?.filiais?.find((f) => f.ativa)?.id
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
    if (usuario?.perfil !== 'COPEIRA' || usuario.troca_senha_obrigatoria || !filialPresenca) return
    const controller = new AbortController()
    const token = localStorage.getItem('token')
    async function confirmar() {
      if (localStorage.getItem('token') !== token) return
      try {
        await api.post('/auth/presenca', { filial_id: filialPresenca }, { signal: controller.signal, ignorarRedirecionamento401: true })
        if (!controller.signal.aborted) setPlantaoOnline(true)
      } catch (erro) {
        if (controller.signal.aborted) return
        setPlantaoOnline(false)
        if (erro.response?.status === 401) setUsuario(null)
      }
    }
    confirmar()
    const intervalo = setInterval(confirmar, 30000)
    const aoVoltar = () => { if (!document.hidden) confirmar() }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => { controller.abort(); clearInterval(intervalo); document.removeEventListener('visibilitychange', aoVoltar) }
  }, [usuario?.id, usuario?.perfil, usuario?.troca_senha_obrigatoria, filialPresenca])

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
