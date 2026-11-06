export function formularioEmail(config = {}) {
  return { modo: config.modo || 'SMTP', remetente: config.remetente || '', habilitado: Boolean(config.habilitado),
    servidor: config.servidor || '', porta: String(config.porta ?? 587), seguranca: config.seguranca || 'STARTTLS',
    autenticar: config.autenticar ?? true, usuario: config.usuario || '', senha_app: '',
    servidor_secundario: config.servidor_secundario || '', porta_secundaria: String(config.porta_secundaria ?? ''),
    tempo_limite: String(config.tempo_limite ?? 30), endereco_resposta: config.endereco_resposta || '' }
}

export function escolherModeloEmail(form, modo) {
  if (modo === 'SMTP') return { ...form, modo, senha_app: '' }
  const autenticar = modo === 'GOOGLE_APP'
  return { ...form, modo, senha_app: '', servidor: autenticar ? 'smtp.gmail.com' : 'smtp-relay.gmail.com',
    porta: '587', seguranca: 'STARTTLS', autenticar, usuario: autenticar ? form.remetente : '' }
}

export function corpoConfiguracaoEmail(form) {
  return { modo: form.modo, remetente: form.remetente.trim(), habilitado: form.habilitado,
    servidor: form.servidor.trim(), porta: Number(form.porta), seguranca: form.seguranca,
    autenticar: form.autenticar, usuario: form.autenticar ? form.usuario.trim() : null,
    servidor_secundario: form.servidor_secundario.trim() || null,
    porta_secundaria: form.porta_secundaria ? Number(form.porta_secundaria) : null,
    tempo_limite: Number(form.tempo_limite), endereco_resposta: form.endereco_resposta.trim() || null,
    ...(form.autenticar && form.senha_app.length ? { senha: form.senha_app } : {}) }
}

export function configuracaoEmailAlterada(form, config) {
  const anterior = formularioEmail(config)
  return Object.keys(anterior).some((k) => form[k] !== anterior[k])
}

export function enderecoAdminLocal(origem) {
  const url = new URL(origem)
  url.hostname = '127.0.0.1'; url.pathname = '/admin'; url.search = ''; url.hash = ''
  return url.href
}
