/** Ícones decorativos de traço suave; as ações mantêm seus rótulos de texto. */
const DESENHOS = {
    folha: <><path d="M19 4c-8-1-14 3-14 9a6 6 0 0 0 6 6c6 0 9-7 8-15Z" /><path d="m5 20 9-10M9 16v-5m0 5h5" /></>,
    refeicao: <><path d="M3 12h18a9 9 0 0 1-18 0ZM5 21h14M8 4v4m4-5v5m4-4v4" /></>,
    pessoas: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2" /></>,
    profissional: <><path d="M5 3v5a5 5 0 0 0 10 0V3M3 3h4m6 0h4M10 13v3a5 5 0 0 0 10 0v-2" /><circle cx="20" cy="11" r="2" /></>,
    seta: <path d="M4 12h16m-6-6 6 6-6 6" />,
    voltar: <path d="M20 12H4m6-6-6 6 6 6" />,
    conferir: <path d="m5 12 4 4L19 6" />,
    cuidado: <><path d="M12 21S3 15.5 3 8.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 9 1.5C21 15.5 12 21 12 21Z" /><path d="M7 12h3l2-3 2 6 2-3h2" /></>,
    escudo: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
    relogio: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    entrega: <><path d="M3 7h11v11H3zM14 11h4l3 4v3h-7M3 4h8" /><circle cx="7" cy="19" r="2" /><circle cx="18" cy="19" r="2" /></>,
    gestao: <><path d="M4 20h16M7 16v-5m5 5V7m5 9V4" /></>,
    ajustes: <><path d="M4 7h9m4 0h3M4 17h3m4 0h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
    unidade: <><path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16M3 21h18M9 21v-5h6v5M9 7h1m4 0h1M9 11h1m4 0h1" /></>,
    prancheta: <><path d="M8 4H6a2 2 0 0 0-2 2v14h16V6a2 2 0 0 0-2-2h-2M8 10h8M8 14h6" /><rect x="8" y="2" width="8" height="4" rx="2" /></>,
    impressora: <><path d="M7 8V3h10v5M7 17H4V9h16v8h-3M7 14h10v7H7zM17 11h.01" /></>,
    chave: <><circle cx="8" cy="9" r="5" /><path d="m12 13 8 8m-3-3 3-3m-6 0 3-3" /></>,
    historico: <><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2" /></>,
}

export function Icone({ nome = 'folha', tamanho = 24, className = '' }) {
  return <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" className={className}>
    {DESENHOS[nome] || DESENHOS.folha}
  </svg>
}

export function MarcaCnutri({ compacto = false }) {
  return <div className={`marca-cnutri ${compacto ? 'marca-compacta' : ''}`} aria-label="Cnutri · Gestão de alimentação e cuidado">
    <span className="marca-simbolo"><img src="/cnutri-icon-v2.png" width="32" height="40" alt="" /></span>
    <span><span className="marca-nome">Cnutri<span className="marca-ponto">.</span></span>
      {!compacto && <span className="marca-descricao">Alimentação e cuidado</span>}</span>
  </div>
}

export function IlustracaoCuidado() {
  return <div className="ilustracao-cuidado" aria-hidden="true">
    <span className="cuidado-orbita cuidado-orbita-externa" /><span className="cuidado-orbita cuidado-orbita-interna" />
    <span className="cuidado-folha"><Icone nome="folha" tamanho={64} /></span>
    <span className="cuidado-prato"><Icone nome="refeicao" tamanho={100} /></span>
    <span className="cuidado-coracao"><Icone nome="cuidado" tamanho={32} /></span>
  </div>
}

export function NotaCuidado({ children, icone = 'cuidado', className = '' }) {
  return <div className={`nota-cuidado ${className}`}><span className="nota-icone"><Icone nome={icone} tamanho={21} /></span><div>{children}</div></div>
}

export function Indicador({ titulo, valor, icone = 'refeicao', detalhe }) {
  return <div className="indicador-cuidado"><span className="indicador-icone"><Icone nome={icone} /></span>
    <div><p className="text-sm text-slate-700">{titulo}</p><p className="indicador-valor">{valor}</p>{detalhe && <p className="text-xs text-slate-700">{detalhe}</p>}</div>
  </div>
}
