import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../services/api.js'
import { destinoAposLogin, useAuth } from '../context/auth.js'
import { MAX_SENHA, MIN_SENHA, PADRAO_SENHA, REGRA_SENHA, senhaValida } from '../services/politicaSenha.js'

export default function Senha() {
  const { usuario, entrar, sair } = useAuth()
  const [parametros] = useSearchParams()
  const navegar = useNavigate()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirmacao, setConfirmacao] = useState('')
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)

  async function salvar(evento) {
    evento.preventDefault()
    setErro('')
    if (nova !== confirmacao) { setErro('A confirmação deve ser igual à nova senha.'); return }
    if (!senhaValida(nova)) { setErro(REGRA_SENHA); return }
    setSalvando(true)
    try {
      const { data } = await api.post('/auth/senha', { senha_atual: atual, nova_senha: nova })
      const sessao = entrar(data)
      navegar(destinoAposLogin(sessao, parametros), { replace: true })
    } catch (e) {
      const detalhe = e.response?.data?.detail
      setErro(Array.isArray(detalhe) ? detalhe.map((d) => d.msg.replace(/^Value error, /, '')).join('. ') : detalhe || 'Não foi possível alterar a senha.')
    } finally { setSalvando(false) }
  }

  const campo = 'mt-1 min-h-12 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-base outline-none focus:border-brand'
  if (usuario.origem_autenticacao === 'AD') return <main className="flex min-h-screen items-center justify-center bg-app-background p-4 text-slate-900">
    <div className="w-full max-w-md space-y-5 rounded-xl bg-panel p-6">
      <h1 className="text-2xl font-bold">Senha da rede</h1>
      <p>Sua senha é administrada pelo Active Directory. Para alterar ou recuperar a senha, siga o procedimento da TI.</p>
      <button onClick={() => navegar(destinoAposLogin(usuario, parametros))} className="font-semibold text-brand underline">Voltar ao painel</button>
    </div>
  </main>
  return <main className="flex min-h-screen items-center justify-center bg-app-background p-4 text-slate-900">
    <form onSubmit={salvar} className="w-full max-w-md space-y-5 rounded-2xl border-t-4 border-brand-vibrant bg-panel p-6 shadow-xl sm:p-8">
      <div><p className="text-sm font-semibold text-brand">Cnutri · {usuario.nome}</p><h1 className="mt-2 text-2xl font-bold">{usuario.troca_senha_obrigatoria ? 'Defina sua nova senha' : 'Alterar minha senha'}</h1></div>
      {usuario.troca_senha_obrigatoria && <p className="rounded-lg bg-brand-soft p-3 text-sm text-brand-ink">Substitua a senha temporária fornecida pela TI para acessar o sistema.</p>}
      {erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-900">{erro}</p>}
      <label className="block text-sm font-semibold">Senha atual<input required type="password" autoComplete="current-password" className={campo} value={atual} onChange={(e) => setAtual(e.target.value)} /></label>
      <label className="block text-sm font-semibold">Nova senha<input required type="password" autoComplete="new-password" minLength={MIN_SENHA} maxLength={MAX_SENHA} pattern={PADRAO_SENHA} title={REGRA_SENHA} aria-describedby="regra-senha" className={campo} value={nova} onChange={(e) => setNova(e.target.value)} /></label>
      <p id="regra-senha" className="text-xs text-slate-700">{REGRA_SENHA}</p>
      <label className="block text-sm font-semibold">Confirmar nova senha<input required type="password" autoComplete="new-password" minLength={MIN_SENHA} maxLength={MAX_SENHA} className={campo} value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} /></label>
      <button disabled={salvando} className="min-h-12 w-full rounded-lg bg-brand px-4 py-3 font-bold text-white hover:bg-brand-hover disabled:opacity-50">{salvando ? 'Salvando…' : 'Salvar nova senha'}</button>
      <div className="flex flex-wrap gap-4 text-sm">
        {!usuario.troca_senha_obrigatoria && <button type="button" onClick={() => navegar(destinoAposLogin(usuario, parametros))} className="font-semibold text-brand underline">Voltar ao painel</button>}
        <button type="button" onClick={sair} className="font-semibold text-slate-700 underline">Sair</button>
      </div>
    </form>
  </main>
}
