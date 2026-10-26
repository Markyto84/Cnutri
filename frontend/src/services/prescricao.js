export function exigeReferencia(tipo, valores = {}) {
  const destino = String(valores.para || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase()
  return tipo !== 'MEDICO' && destino !== 'ACOMPANHANTE'
}

export function horarioLocalPrescricao(valor) {
  if (!valor) return ''
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(valor)).replace(' ', 'T').replace(/:00$/, '')
}

export function referenciaPayload(valor) {
  const horario = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(valor.data_hora || '') ? `${valor.data_hora}:00` : valor.data_hora
  return { referencia: (valor.referencia || '').trim(), data_hora: `${horario}-03:00`,
    prescritor_nome: (valor.prescritor_nome || '').trim(), prescritor_registro: (valor.prescritor_registro || '').trim() }
}

export function corpoPedido(valores, original, prescricao) {
  const fixos = ['leito', 'prontuario', 'nome_paciente', 'dieta_id', 'observacoes_alergias', 'solicitante_nome']
  return { ...Object.fromEntries(fixos.filter((k) => original[k] !== undefined).map((k) => [k, original[k]])),
    ...Object.fromEntries(Object.entries(valores).filter(([k]) => fixos.includes(k))),
    dados_dinamicos: Object.fromEntries(Object.entries(valores).filter(([k]) => !fixos.includes(k))),
    tipo_solicitacao: original.tipo_solicitacao, solicitante_nome: original.solicitante_nome,
    solicitante_identificacao: original.solicitante_identificacao,
    dieta_id: valores.dieta_id !== undefined ? (valores.dieta_id ? Number(valores.dieta_id) : null) : original.dieta_id,
    prescricao: exigeReferencia(original.tipo_solicitacao, valores) ? referenciaPayload(prescricao) : null }
}
