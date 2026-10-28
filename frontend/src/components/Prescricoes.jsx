import { useEffect, useRef, useState } from 'react'
import { api } from '../services/api.js'
import { MARCA } from '../services/marca.js'
import { useConsultaGestao } from '../hooks/useConsultaGestao.js'
import { horarioBrasilia, mensagemErro } from '../services/painelOperacional.js'
import { corpoPedido } from '../services/prescricao.js'
import { CAMPO, FiltroUnidade, Paginacao, PRIMARIO, SECUNDARIO } from './ConsultaGestao.jsx'
import FormDinamico from './FormDinamico.jsx'

const ACOES = { SOLICITADO: 'Solicitação registrada', PEDIDO_CORRIGIDO: 'Pedido corrigido', VINCULO_CONFERIDO: 'Vínculo com prescrição conferido',
  ETAPA_ALTERADA: 'Etapa alterada', RETIRADA_REGISTRADA: 'Retirada registrada', COPEIRA_IDENTIFICADA_QR: 'Copeira identificada pelo QR Code', ENTREGA_REGISTRADA: 'Entrega registrada', ENTREGA_CONFIRMADA_QR: 'Recebimento confirmado por QR Code' }
const ROTULOS = { solicitante_nome: 'Solicitante informado', solicitante_identificacao: 'Registro do solicitante',
  nome_paciente: 'Paciente', prontuario: 'Prontuário', leito: 'Leito', dieta_id: 'ID da dieta', dieta_nome: 'Dieta',
  observacoes_alergias: 'Restrições / alergias / observações', dados_dinamicos: 'Respostas do formulário', prescricao: 'Referência da prescrição',
  status: 'Situação', versao: 'Versão', tipo_solicitacao: 'Formulário', referencia: 'Referência', data_hora: 'Data e hora (Brasília)',
  prescritor_nome: 'Prescritor informado', prescritor_registro: 'Registro do prescritor', situacao: 'Situação do vínculo',
  conferida_por_usuario_id: 'Conta da conferência', conferida_por_nome: 'Conferido por', conferida_em: 'Conferido em (Brasília)',
  andar: 'Andar', refeicao: 'Refeição', cardapio: 'Cardápio', cardapio_acompanhante: 'Cardápio do acompanhante', matricula: 'Matrícula',
  data_nascimento: 'Data de nascimento', internado_mais_6h: 'Internado há mais de 6 horas', liquido_espessado: 'Líquido espessado' }

export default function Prescricoes({ filialId, filiais = [] }) {
  const [unidade, setUnidade] = useState(filialId || filiais[0]?.id || '')
  const [busca, setBusca] = useState('')
  const [pagina, setPagina] = useState(1)
  const [selecionado, setSelecionado] = useState(null)
  const consulta = useConsultaGestao('/assistencia/pedidos', { filial_id: unidade, busca, pagina })
  return <section className="space-y-4" aria-label="Pedidos e rastreabilidade">
    <div><h2 className="text-xl font-bold">Pedidos e rastreabilidade</h2>
      <p className="mt-1 text-sm text-slate-700">Solicitações, correções e responsáveis pelas etapas das refeições dos pacientes.</p></div>
    <div className="grid gap-3 rounded-xl bg-panel p-4 sm:grid-cols-2">
      {filiais.length > 0 && <FiltroUnidade filiais={filiais} valor={unidade} todas={false} onChange={(v) => { setUnidade(v); setPagina(1); setSelecionado(null) }} />}
      <label className="text-sm font-semibold">Buscar por pedido, paciente ou prontuário
        <input className={CAMPO} maxLength={100} value={busca} onChange={(e) => { setBusca(e.target.value); setPagina(1) }} /></label>
    </div>
    {consulta.erro && <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">{consulta.erro}</p>}
    {consulta.carregando && <p>Carregando solicitações…</p>}
    <div className="grid gap-3 lg:grid-cols-2">{consulta.dados?.itens.map((p) => <article key={p.id} className="min-w-0 rounded-xl bg-panel p-4">
      <div className="flex flex-wrap justify-between gap-2"><h3 className="break-words font-bold">#{p.id} · {p.nome_paciente}</h3><span className="text-sm">{p.status.replaceAll('_', ' ')}</span></div>
      <p className="mt-2 text-sm">{p.dieta?.nome || 'Dieta não informada'} · Leito {p.leito || 'não informado'} · Versão {p.versao}</p>
      {p.prescricao && <p className="mt-2 text-sm">Informações anteriores de prescrição disponíveis no histórico.</p>}
      <button className={`${PRIMARIO} mt-3`} onClick={() => setSelecionado(p.id)}>Abrir pedido e histórico</button>
    </article>)}</div>
    {consulta.dados && <><Paginacao pagina={pagina} total={consulta.dados.total} tamanho={25} onChange={setPagina} />
      {!consulta.dados.total && <p className="rounded-xl bg-panel p-5">Nenhuma solicitação encontrada.</p>}</>}
    {selecionado && <DetalhePedido key={selecionado} pedidoId={selecionado} onFechar={() => setSelecionado(null)} onAtualizar={consulta.atualizar} />}
  </section>
}

function DetalhePedido({ pedidoId, onFechar, onAtualizar }) {
  const dialogo = useRef(null)
  const [aba, setAba] = useState('dados')
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [revisao, setRevisao] = useState(0)
  const [detalhe, setDetalhe] = useState(null)
  const [dietas, setDietas] = useState([])
  useEffect(() => { const d = dialogo.current; d.showModal(); return () => { if (d.open) d.close() } }, [])
  useEffect(() => {
    const controller = new AbortController()
    api.get(`/assistencia/pedidos/${pedidoId}`, { signal: controller.signal })
      .then(async ({ data }) => {
        const catalogo = await api.get('/gestao/dietas', { params: { filial_id: data.pedido.filial_id }, signal: controller.signal })
        if (!controller.signal.aborted) { setDetalhe(data); setDietas(catalogo.data.filter((d) => d.ativa)) }
      }).catch((e) => { if (!controller.signal.aborted) { setErro(mensagemErro(e)); setDetalhe(null) } })
    return () => controller.abort()
  }, [pedidoId, revisao])
  const pedido = detalhe?.pedido
  const ativa = ['PENDENTE', 'EM_PREPARO', 'PRONTO'].includes(pedido?.status)
  function atualizar(mensagem) { setAviso(mensagem); setAba('dados'); setDetalhe(null); setRevisao((v) => v + 1); onAtualizar() }
  function exportarHistorico() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(detalhe, null, 2)], { type: 'application/json;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `${MARCA.prefixoArquivos}-historico-pedido-${pedidoId}.json`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <dialog ref={dialogo} onCancel={(e) => { e.preventDefault(); if (!salvando) onFechar() }} aria-labelledby="titulo-prescricao"
    className="m-auto max-h-[92dvh] overflow-y-auto rounded-2xl bg-panel p-4 text-slate-900 shadow-2xl backdrop:bg-black/60 sm:p-6" style={{ width: 'min(58rem, calc(100vw - 1rem))' }}>
    <div className="mb-4 flex items-start justify-between gap-3"><h2 id="titulo-prescricao" className="text-xl font-bold">Pedido #{pedidoId}</h2>
      <button disabled={salvando} className={SECUNDARIO} onClick={onFechar}>Fechar</button></div>
    {erro && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-red-800">{erro}</p>}
    {aviso && <p role="status" className="mb-4 rounded-lg bg-emerald-50 p-3 text-emerald-900">{aviso}</p>}
    {!detalhe ? <p>Carregando dados…</p> : <>
      <p className="mb-4 break-words font-semibold">{pedido.nome_paciente} · {pedido.status.replaceAll('_', ' ')} · Versão {pedido.versao}</p>
      <nav className="mb-5 flex flex-wrap gap-2" aria-label="Dados do pedido">{[['dados', 'Dados e responsáveis'], ['corrigir', 'Corrigir pedido'], ['historico', 'Histórico']].map(([id, titulo]) =>
        <button key={id} disabled={salvando || (id === 'corrigir' && !ativa)} onClick={() => { setAba(id); setErro('') }} className={aba === id ? PRIMARIO : SECUNDARIO}>{titulo}</button>)}</nav>
      {aba === 'dados' && <div className="space-y-5">
        <dl className="grid gap-3 rounded-xl bg-white p-4 sm:grid-cols-2">
          <Dado titulo="Prontuário" valor={pedido.prontuario} /><Dado titulo="Dieta" valor={pedido.dieta?.nome} />
          <Dado titulo="Solicitante informado no formulário" valor={`${pedido.solicitante_nome || 'Não registrado'} · ${pedido.solicitante_identificacao}`} />
          <Dado titulo="Solicitado em" valor={horarioBrasilia(/(?:Z|[+-]\d{2}:\d{2})$/.test(pedido.criado_em) ? pedido.criado_em : `${pedido.criado_em}Z`)} />
        </dl>
        {pedido.prescricao && <section className="space-y-3 rounded-xl bg-brand-soft p-4">
          <h3 className="font-bold">Informações anteriores de prescrição</h3>
          <p className="text-sm">Dados preservados para consulta. A prescrição não integra o formulário atual de solicitação.</p>
          <dl className="grid gap-3 sm:grid-cols-2">
            <Dado titulo="Referência registrada" valor={pedido.prescricao.referencia} />
            <Dado titulo="Data e hora registradas" valor={horarioBrasilia(pedido.prescricao.data_hora)} />
            <Dado titulo="Prescritor informado" valor={pedido.prescricao.prescritor_nome} />
            <Dado titulo="Registro do prescritor" valor={pedido.prescricao.prescritor_registro} />
          </dl>
          {pedido.prescricao.situacao === 'CONFERIDA' && <p className="text-sm">Conferência anterior registrada por {pedido.prescricao.conferida_por_nome} em {horarioBrasilia(pedido.prescricao.conferida_em)}.</p>}
        </section>}
        <div><h3 className="mb-2 font-bold">Etapas e responsáveis registrados</h3>
          {!detalhe.etapas.length && <p className="text-sm">Sem mudanças de etapa registradas.</p>}
          <ol className="space-y-2">{detalhe.etapas.map((e, i) => <li key={i} className="rounded-lg bg-white p-3 text-sm">
            {e.anterior || 'Início'} → {e.nova} · {horarioBrasilia(e.data_hora)}<br />
            {e.usuario_id ? `${e.nome_atual_usuario || 'Usuário'} · conta #${e.usuario_id} (nome atual do cadastro)`
              : e.nova === 'ENTREGUE' && detalhe.entrega?.recebedor_registro_profissional ? `Recebedor informado: ${[detalhe.entrega.recebedor_nome, detalhe.entrega.recebedor_registro_profissional].filter(Boolean).join(' · ')} · QR Code` : 'Autor não registrado na época'}</li>)}</ol>
        </div>
        {detalhe.entrega && <dl className="grid gap-3 rounded-xl bg-white p-4 sm:grid-cols-2"><Dado titulo="Copeira responsável" valor={detalhe.entrega.copeira_nome} />
          <Dado titulo="Entrega registrada pela conta" valor={detalhe.entrega.registrado_por_usuario_id ? `#${detalhe.entrega.registrado_por_usuario_id}` : ''} />
          <Dado titulo="Recebedor" valor={detalhe.entrega.recebedor_nome} /><Dado titulo="Entregue em" valor={horarioBrasilia(detalhe.entrega.entregue_em)} />
          <Dado titulo="Registro profissional do recebedor" valor={detalhe.entrega.recebedor_registro_profissional} />
          <Dado titulo="Confirmação da entrega" valor={detalhe.entrega.origem_entrega} />
          <Dado titulo="Assinatura de recebimento" valor={detalhe.entrega.assinatura_registrada ? 'Registrada' : 'Não registrada'} /></dl>}
      </div>}
      {aba === 'corrigir' && ativa && detalhe.formulario && <Correcao key={`${pedido.id}:${pedido.versao}`} detalhe={detalhe} dietas={dietas} salvando={salvando}
        setSalvando={setSalvando} onErro={setErro} onSalvo={atualizar} onCancelar={() => setAba('dados')} />}
      {aba === 'historico' && <div className="space-y-3">
        <p className="text-sm">Os eventos abaixo preservam autor e valores registrados a partir desta atualização. A solicitação pública identifica o solicitante por declaração; uma conta autenticada, quando presente, é registrada separadamente.</p>
        <button className={SECUNDARIO} onClick={exportarHistorico}>Baixar histórico completo (JSON)</button>
        {!detalhe.eventos.length && <p>Sem eventos detalhados anteriores disponíveis. Consulte as etapas registradas.</p>}
        {[...detalhe.eventos].reverse().map((e) => <article key={e.id} className="space-y-2 rounded-xl bg-white p-4">
          <h3 className="font-bold">{ACOES[e.acao] || e.acao}</h3><p className="text-sm">{horarioBrasilia(e.criado_em)} · {e.autor_nome ? `${e.autor_nome} · ${e.autor_perfil} · conta #${e.autor_usuario_id}` : 'Envio público · identidade declarada no formulário'}</p>
          {e.motivo && <p className="whitespace-pre-line text-sm"><strong>Motivo:</strong> {e.motivo}</p>}
          <details open={e.acao === 'PEDIDO_CORRIGIDO'}><summary className="cursor-pointer py-2 text-sm font-semibold">Ver {e.antes ? 'alterações' : 'dados registrados'}</summary>
            <div className="space-y-2">{Object.entries(e.depois || {}).filter(([k, v]) => JSON.stringify(e.antes?.[k]) !== JSON.stringify(v)).map(([k, v]) => <div key={k} className="rounded-lg bg-slate-50 p-3 text-sm">
              <p className="font-semibold">{ROTULOS[k] || k.replaceAll('_', ' ')}</p>{e.antes && <p className="mt-1 whitespace-pre-wrap break-words">Antes: {texto(e.antes[k], k)}</p>}
              <p className="mt-1 whitespace-pre-wrap break-words">Registrado: {texto(v, k)}</p></div>)}</div>
          </details>
        </article>)}
      </div>}
    </>}
  </dialog>
}

function texto(valor, chave = '') {
  if (valor == null || valor === '') return 'Não registrado'
  if (['data_hora', 'conferida_em'].includes(chave)) return horarioBrasilia(valor)
  if (chave === 'data_nascimento' && /^\d{4}-\d{2}-\d{2}$/.test(valor)) return valor.split('-').reverse().join('/')
  if (typeof valor === 'object') return Object.entries(valor).map(([k, v]) => `${ROTULOS[k] || k.replaceAll('_', ' ')}: ${texto(v, k)}`).join('\n')
  return String(valor)
}

function Dado({ titulo, valor }) { return <div className="min-w-0"><dt className="text-xs font-semibold text-slate-600">{titulo}</dt><dd className="mt-1 break-words text-sm">{valor || 'Não registrado'}</dd></div> }

function Correcao({ detalhe, dietas, salvando, setSalvando, onErro, onSalvo, onCancelar }) {
  const pedido = detalhe.pedido
  const [motivo, setMotivo] = useState('')
  const [substituir, setSubstituir] = useState(false)
  const valores = { ...pedido.dados_dinamicos, leito: pedido.leito || '', prontuario: pedido.prontuario || '', nome_paciente: pedido.nome_paciente,
    dieta_id: pedido.dieta_id || '', observacoes_alergias: pedido.observacoes_alergias || '' }
  const campos = detalhe.formulario.campos
  const ids = new Set(campos.map((c) => c.id))
  // O formulário vigente deixa explícitos os valores exigidos para a nova versão.
  const iniciais = Object.fromEntries(Object.entries(valores).filter(([k]) => ids.has(k)))
  async function salvar(dados) {
    setSalvando(true); onErro('')
    try {
      const { data } = await api.put(`/assistencia/pedidos/${pedido.id}`, { versao: pedido.versao, motivo,
        confirmar_substituicao: substituir, pedido: corpoPedido(dados, pedido) })
      onSalvo(data.mensagem)
    } catch (e) { onErro(mensagemErro(e)) } finally { setSalvando(false) }
  }
  return <FormDinamico titulo="Corrigir solicitação do paciente" campos={campos} dietas={dietas} valoresIniciais={iniciais} enviando={salvando}
    onEnviar={salvar} onCancelar={onCancelar} textoBotao="Salvar correção e retornar a Pendentes"
    complemento={() => <div className="space-y-4">
      <label className="block text-sm font-semibold">Motivo da correção *<textarea className={CAMPO} required minLength={5} maxLength={1000} rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
      <p className="text-sm">A versão anterior será preservada e o pedido voltará a Pendentes para a cozinha preparar a versão atual.</p>
      {detalhe.documentos_emitidos && <label className="flex items-start gap-3 rounded-lg bg-amber-50 p-3 text-sm"><input type="checkbox" required checked={substituir} onChange={(e) => setSubstituir(e.target.checked)} className="mt-1 h-5 w-5 shrink-0" />
        Confirmo que substituirei com a cozinha as filipetas e etiquetas anteriores, inclusive documentos cujo envio ficou incerto.</label>}
    </div>} />
}
