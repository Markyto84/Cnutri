import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { BOTAO } from './Operacao.jsx'

function dataHoje() {
  const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const valor = (tipo) => partes.find((p) => p.type === tipo).value
  return `${valor('year')}-${valor('month')}-${valor('day')}`
}

const horario = (valor) => new Date(valor).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })

export default function RelatorioEntregas({ filialId }) {
  const [inicio, setInicio] = useState(dataHoje)
  const [fim, setFim] = useState(dataHoje)
  const [consulta, setConsulta] = useState(() => ({ data_inicio: dataHoje(), data_fim: dataHoje(), pagina: 1, versao: 0 }))
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    const iniciar = setTimeout(async () => {
      setCarregando(true)
      setResultado(null)
      setErro('')
      try {
        const { versao: _versao, ...filtros } = consulta
        const { data } = await api.get('/relatorios/entregas', { params: { filial_id: filialId, ...filtros }, signal: controller.signal })
        if (!controller.signal.aborted) setResultado(data)
      } catch (e) {
        if (!controller.signal.aborted) setErro(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Não foi possível carregar o relatório de entregas')
      } finally { if (!controller.signal.aborted) setCarregando(false) }
    }, 0)
    return () => { clearTimeout(iniciar); controller.abort() }
  }, [filialId, consulta])

  function filtrar(evento) {
    evento.preventDefault()
    if (inicio && fim && inicio > fim) { setErro('A data inicial deve ser anterior ou igual à data final'); return }
    setConsulta((atual) => ({ data_inicio: inicio || undefined, data_fim: fim || undefined, pagina: 1, versao: atual.versao + 1 }))
  }

  return <section className="min-w-0 rounded-xl bg-panel p-4 md:col-span-3 sm:p-5" aria-labelledby="relatorio-entregas">
    <h3 id="relatorio-entregas" className="text-lg font-bold">Entregas e comprovantes de recebimento</h3>
    <p className="mt-1 text-sm text-slate-700">Responsável pela entrega e data e hora da conclusão. Os comprovantes anteriores continuam disponíveis. Horário de Brasília.</p>
    <form onSubmit={filtrar} className="my-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
      <label className="min-w-0 text-sm font-semibold">Data inicial<input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} className="mt-1 min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-base font-normal" /></label>
      <label className="min-w-0 text-sm font-semibold">Data final<input type="date" value={fim} onChange={(e) => setFim(e.target.value)} className="mt-1 min-h-11 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 text-base font-normal" /></label>
      <button className={`${BOTAO} bg-brand text-white`}>Consultar entregas</button>
    </form>
    {erro && <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-900">{erro}</p>}
    {carregando && <p role="status" className="py-4 text-sm">Carregando entregas…</p>}
    {resultado && <>
      <p className="mb-3 text-sm font-semibold">{resultado.total} entrega(s) no período</p>
      {!resultado.itens.length && <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-700">Nenhuma entrega encontrada no período selecionado.</p>}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">{resultado.itens.map((item) => <Comprovante key={item.pedido_id} item={item} filialId={filialId} />)}</div>
      {resultado.total_paginas > 1 && <nav aria-label="Páginas do relatório de entregas" className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button disabled={resultado.pagina <= 1} onClick={() => setConsulta((c) => ({ ...c, pagina: c.pagina - 1 }))} className={`${BOTAO} bg-slate-50`}>Anterior</button>
        <span className="text-sm">Página {resultado.pagina} de {resultado.total_paginas}</span>
        <button disabled={resultado.pagina >= resultado.total_paginas} onClick={() => setConsulta((c) => ({ ...c, pagina: c.pagina + 1 }))} className={`${BOTAO} bg-slate-50`}>Próxima</button>
      </nav>}
    </>}
  </section>
}

function Comprovante({ item, filialId }) {
  const [aberto, setAberto] = useState(false)
  return <article className="min-w-0 space-y-3 break-words rounded-xl bg-slate-50 p-4">
    <div><p className="text-xs text-slate-700">Pedido #{item.pedido_id} · {item.tipo_solicitacao === 'MEDICO' ? 'Profissional' : 'Paciente'}</p><h4 className="mt-1 font-bold">{item.destinatario || 'Destinatário não informado'}</h4></div>
    <p className="text-sm font-semibold text-brand-ink">{item.refeicao || 'Refeição não informada'}</p>
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <div><dt className="text-slate-700">Solicitante</dt><dd className="font-semibold">{item.solicitante_nome || 'Não registrado'}{item.solicitante_identificacao && ` · ${item.solicitante_identificacao}`}</dd></div>
      <div><dt className="text-slate-700">Copeira</dt><dd className="font-semibold">{item.copeira_nome}</dd></div>
      <div><dt className="text-slate-700">Registrado por</dt><dd className="font-semibold">{item.registrado_por_nome || 'Não registrado na entrega antiga'}</dd></div>
      {item.recebedor_nome && <div><dt className="text-slate-700">Recebedor</dt><dd className="font-semibold">{item.recebedor_nome}</dd></div>}
      <div><dt className="text-slate-700">Data e hora da entrega</dt><dd className="font-semibold">{horario(item.entregue_em)}</dd></div>
      <div><dt className="text-slate-700">Local / leito</dt><dd>{[item.local_entrega, item.leito && `Leito ${item.leito}`].filter(Boolean).join(' · ') || 'Não informado'}</dd></div>
    </dl>
    {item.assinatura_disponivel ? <>
      <button onClick={() => setAberto((valor) => !valor)} aria-expanded={aberto} className={`${BOTAO} bg-white text-brand-ink`}>{aberto ? 'Ocultar assinatura' : 'Ver assinatura'}</button>
      {aberto && <ImagemAssinatura filialId={filialId} pedidoId={item.pedido_id} recebedor={item.recebedor_nome} />}
    </> : <p className="text-xs text-slate-700">Entrega finalizada sem assinatura registrada.</p>}
  </article>
}

function ImagemAssinatura({ filialId, pedidoId, recebedor }) {
  const [url, setUrl] = useState('')
  const [erro, setErro] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let imagem
    api.get(`/relatorios/entregas/${pedidoId}/assinatura`, { params: { filial_id: filialId }, responseType: 'blob', signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { imagem = URL.createObjectURL(data); setUrl(imagem) } })
      .catch(() => { if (!controller.signal.aborted) setErro(true) })
    return () => { controller.abort(); if (imagem) URL.revokeObjectURL(imagem) }
  }, [filialId, pedidoId])
  if (erro) return <p role="alert" className="text-sm text-red-800">Não foi possível carregar a assinatura. Feche e abra novamente.</p>
  return url ? <img src={url} alt={`Assinatura de ${recebedor}`} className="w-full rounded-lg border border-slate-300 bg-white" /> : <p role="status" className="text-sm">Carregando assinatura…</p>
}
