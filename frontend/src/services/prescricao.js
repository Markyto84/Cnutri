export function corpoPedido(valores, original) {
  const fixos = ['leito', 'prontuario', 'nome_paciente', 'dieta_id', 'observacoes_alergias', 'solicitante_nome']
  return { ...Object.fromEntries(fixos.filter((k) => original[k] !== undefined).map((k) => [k, original[k]])),
    ...Object.fromEntries(Object.entries(valores).filter(([k]) => fixos.includes(k))),
    dados_dinamicos: Object.fromEntries(Object.entries(valores).filter(([k]) => !fixos.includes(k))),
    tipo_solicitacao: original.tipo_solicitacao, solicitante_nome: original.solicitante_nome,
    solicitante_identificacao: original.solicitante_identificacao,
    dieta_id: valores.dieta_id !== undefined ? (valores.dieta_id ? Number(valores.dieta_id) : null) : original.dieta_id }
}
