import { Icone, MarcaCnutri } from '../components/Identidade.jsx'

function OrientacaoDeAcesso({ titulo, codigo }) {
  return <main className="auth-shell">
    <section className="receipt-card space-y-5 text-center">
      <MarcaCnutri /><span className="mx-auto flex w-fit rounded-full bg-brand-soft p-4 text-brand"><Icone nome="unidade" tamanho={32} /></span>
      {codigo && <p className="eyebrow">Página {codigo}</p>}
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
