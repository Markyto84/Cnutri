function OrientacaoDeAcesso({ titulo, codigo }) {
  return <main className="flex min-h-screen items-center justify-center bg-app-background p-4 text-slate-900">
    <section className="w-full max-w-lg space-y-4 rounded-2xl bg-panel p-6 text-center shadow-sm sm:p-8">
      <p className="font-semibold text-brand">Cnutri{codigo && ` · ${codigo}`}</p>
      <h1 className="text-2xl font-bold">{titulo}</h1>
      <p className="text-slate-700">Utilize o atalho da sua unidade fornecido pela TI. Se não conseguir acessar, confira o endereço com o suporte.</p>
    </section>
  </main>
}

export function AcessoPorUnidade() {
  return <OrientacaoDeAcesso titulo="Acesse pelo atalho da sua unidade" />
}

export default function NaoEncontrado() {
  return <OrientacaoDeAcesso titulo="Página não encontrada" codigo="404" />
}
