import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { unidadesPublicasApi } from '../services/unidadesPublicas.js'
import { caminhoCozinha } from '../services/rotasUnidades.js'

export default function Inicio() {
  const [unidades, setUnidades] = useState(null)
  const [erro, setErro] = useState(false)
  const [tentativa, setTentativa] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    unidadesPublicasApi.get('/unidades', { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setUnidades(data) })
      .catch(() => { if (!controller.signal.aborted) setErro(true) })
    return () => controller.abort()
  }, [tentativa])

  if (unidades?.length === 1) return <Navigate to={`/${encodeURIComponent(unidades[0].codigo_slug)}`} replace />

  return <main className="min-h-screen bg-app-background p-4 text-slate-900 sm:p-8">
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="brand-header flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <img src="/cnutri-icon-v2.png" alt="" className="h-12 w-12 object-contain" />
          <div><h1 className="text-3xl font-bold text-brand">Cnutri</h1><p className="mt-1 text-sm text-slate-700">Sistema de Gestão de Dietas</p></div>
        </div>
        <Link to="/login" className="rounded-lg bg-slate-50 px-4 py-3 text-sm font-semibold hover:bg-slate-200">Entrar no sistema</Link>
      </header>

      {erro ? <section className="space-y-4 rounded-2xl bg-panel p-6">
        <p role="alert" className="text-red-800">Não foi possível carregar as unidades. Verifique a conexão e tente novamente.</p>
        <button onClick={() => { setErro(false); setUnidades(null); setTentativa((t) => t + 1) }} className="rounded-lg bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-hover">Tentar novamente</button>
      </section> : unidades === null ? <p role="status">Carregando unidades…</p>
        : unidades.length === 0 ? <section className="space-y-2 rounded-2xl bg-panel p-6">
          <h2 className="text-xl font-bold">Nenhuma unidade disponível</h2>
          <p className="text-slate-700">Aguarde a ativação de uma unidade pelo administrador de TI.</p>
        </section> : <section aria-labelledby="titulo-unidades" className="space-y-4">
          <div><h2 id="titulo-unidades" className="text-2xl font-bold">Selecione a unidade</h2>
            <p className="mt-1 text-slate-700">Solicite uma refeição ou acompanhe o preparo na cozinha.</p></div>
          <div className="grid gap-4 md:grid-cols-2">
            {unidades.map((unidade) => <article key={unidade.id} className="flex min-w-0 flex-col justify-between gap-6 rounded-2xl bg-panel p-6 shadow-sm">
              <h3 className="break-words text-xl font-bold">{unidade.nome}</h3>
              <div className="flex flex-wrap gap-3">
                <Link to={`/${encodeURIComponent(unidade.codigo_slug)}`} aria-label={`Solicitar refeição — ${unidade.nome}`} className="rounded-lg bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-hover">Solicitar refeição</Link>
                <Link to={caminhoCozinha(unidade)} aria-label={`Painel da cozinha — ${unidade.nome}`} className="rounded-lg bg-slate-50 px-4 py-3 text-sm font-semibold hover:bg-slate-200">Painel da cozinha</Link>
              </div>
            </article>)}
          </div>
        </section>}
    </div>
  </main>
}
