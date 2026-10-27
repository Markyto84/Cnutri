import { Link } from 'react-router-dom'

export default function NaoEncontrado() {
  return <main className="flex min-h-screen items-center justify-center bg-app-background p-4 text-slate-900">
    <section className="w-full max-w-lg space-y-4 rounded-2xl bg-panel p-6 text-center shadow-sm sm:p-8">
      <p className="font-semibold text-brand">Cnutri · 404</p>
      <h1 className="text-2xl font-bold">Página não encontrada</h1>
      <p className="text-slate-700">Confira o endereço ou escolha uma unidade na página inicial.</p>
      <Link to="/" className="inline-block rounded-lg bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-hover">Ir para o início</Link>
    </section>
  </main>
}
