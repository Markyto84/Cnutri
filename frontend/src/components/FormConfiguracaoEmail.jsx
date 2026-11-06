import { useRef } from 'react'
import { CAMPO, PRIMARIO, SECUNDARIO } from './ConsultaGestao.jsx'
import { escolherModeloEmail, enderecoAdminLocal } from '../services/configuracaoEmail.js'

function Campo({ titulo, children, ajuda }) {
  return <label className="block min-w-0 text-sm font-semibold"><span className="mb-2 block">{titulo}</span>{children}
    {ajuda && <span className="mt-2 block text-xs font-normal text-slate-700">{ajuda}</span>}</label>
}

export default function FormConfiguracaoEmail({ config, form, setForm, ocupado, mudou, salvar, testar }) {
  const formulario = useRef(null)
  const personalizado = form.modo === 'SMTP'
  const alterar = (chave, valor) => setForm((f) => ({ ...f, [chave]: valor }))
  const google = form.modo === 'GOOGLE_APP' || form.servidor.trim().toLowerCase() === 'smtp.gmail.com'
  return <form ref={formulario} onSubmit={salvar} className="space-y-5 rounded-2xl bg-panel p-5" aria-label="Configuração SMTP da unidade">
    <div><h3 className="text-lg font-bold">Configuração SMTP</h3><p className="mt-2 text-sm text-slate-700">Preencha os dados fornecidos pelo serviço de e-mail deste ambiente. A configuração vale para a unidade selecionada.</p></div>
    <Campo titulo="Modelo de configuração"><select className={CAMPO} value={form.modo} disabled={ocupado}
      onChange={(e) => setForm(escolherModeloEmail(form, e.target.value))}>
      <option value="SMTP">SMTP personalizado</option><option value="GOOGLE_APP">Google Workspace · Senha de app</option>
      <option value="GOOGLE_RELAY">Google Workspace · Relay autorizado pela TI</option></select></Campo>
    <div className="grid gap-4 md:grid-cols-2">
      <Campo titulo="E-mail da unidade / remetente"><input className={CAMPO} type="email" required maxLength={254} autoComplete="off"
        placeholder="dietas@empresa.com" value={form.remetente} disabled={ocupado} onChange={(e) => setForm((f) => ({ ...f, remetente: e.target.value,
          ...(f.modo === 'GOOGLE_APP' ? { usuario: e.target.value, senha_app: '' } : {}) }))} /></Campo>
      <Campo titulo="Endereço de resposta (opcional)" ajuda="Recebe as respostas aos avisos. Vazio utiliza o remetente."><input className={CAMPO} type="email" maxLength={254}
        value={form.endereco_resposta} disabled={ocupado} placeholder="Mesmo e-mail do remetente" onChange={(e) => alterar('endereco_resposta', e.target.value)} /></Campo>
      <Campo titulo="Servidor SMTP principal"><input className={CAMPO} required maxLength={253} autoComplete="off" placeholder="smtp.empresa.com ou IP"
        value={form.servidor} disabled={ocupado || !personalizado} onChange={(e) => alterar('servidor', e.target.value)} /></Campo>
      <Campo titulo="Porta SMTP principal"><input className={CAMPO} type="number" required min={1} max={65535}
        value={form.porta} disabled={ocupado || !personalizado} onChange={(e) => alterar('porta', e.target.value)} /></Campo>
      <Campo titulo="Segurança da conexão" ajuda="Conexões TLS validam o certificado do servidor."><select className={CAMPO} value={form.seguranca} disabled={ocupado || !personalizado} onChange={(e) => {
        const seguranca = e.target.value
        setForm((f) => ({ ...f, seguranca, ...(seguranca === 'SEM_TLS' ? { autenticar: false, usuario: '', senha_app: '' } : {}) }))
      }}><option value="STARTTLS">STARTTLS</option><option value="TLS">SSL/TLS</option><option value="SEM_TLS">Sem TLS · Relay sem autenticação</option></select></Campo>
      <Campo titulo="Tempo limite SMTP (segundos)"><input className={CAMPO} type="number" required min={5} max={30} value={form.tempo_limite}
        disabled={ocupado} onChange={(e) => alterar('tempo_limite', e.target.value)} /></Campo>
      <Campo titulo="Autenticação SMTP"><select className={CAMPO} value={form.autenticar ? 'SIM' : 'NAO'} disabled={ocupado || !personalizado || form.seguranca === 'SEM_TLS'}
        onChange={(e) => setForm((f) => ({ ...f, autenticar: e.target.value === 'SIM', senha_app: '', usuario: e.target.value === 'SIM' ? f.usuario || f.remetente : '' }))}>
        <option value="SIM">Usuário e senha</option><option value="NAO">Nenhuma · Relay autorizado</option></select></Campo>
      {form.autenticar && <Campo titulo="Usuário SMTP" ajuda="Pode ser diferente do remetente, conforme o serviço de e-mail."><input className={CAMPO} required maxLength={254}
        autoComplete="off" value={form.usuario} disabled={ocupado || !personalizado} onChange={(e) => setForm((f) => ({ ...f, usuario: e.target.value, senha_app: '' }))} /></Campo>}
    </div>
    <details className="rounded-xl bg-slate-50 p-4">
      <summary className="cursor-pointer text-sm font-semibold text-brand-ink">Servidor SMTP secundário (opcional)</summary>
      <p className="my-3 text-sm text-slate-700">Usado quando o principal falhar sem aceitar a mensagem. Os dois servidores utilizam a mesma segurança e autenticação.</p>
      <div className="grid gap-4 md:grid-cols-2"><Campo titulo="Servidor SMTP secundário"><input className={CAMPO} maxLength={253}
        value={form.servidor_secundario} disabled={ocupado} placeholder="smtp-reserva.empresa.com ou IP" onChange={(e) => alterar('servidor_secundario', e.target.value)} /></Campo>
        <Campo titulo="Porta SMTP secundária"><input className={CAMPO} type="number" min={1} max={65535} value={form.porta_secundaria}
          disabled={ocupado} onChange={(e) => alterar('porta_secundaria', e.target.value)} /></Campo></div>
    </details>
    {form.autenticar ? <>
      {google && <div id="orientacao-senha-google" className="space-y-2 rounded-xl bg-brand-soft p-4 text-sm text-brand-ink">
        <p className="font-bold">O Google exige uma credencial específica para aplicativos.</p>
        <p>Para o Gmail SMTP, utilize a senha de app de 16 caracteres, conforme a política da conta. A senha comum da caixa de e-mail não autoriza essa conexão.</p>
        <a className="font-semibold underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">Abrir Senhas de app no Google</a>
      </div>}
      {!config.protecao_preparada && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">A TI precisa preparar a proteção das credenciais no servidor antes de cadastrar a senha.</p>}
      {!config.acesso_seguro && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Cadastre a senha usando HTTPS ou, no próprio computador do servidor, <a className="underline" href={enderecoAdminLocal(window.location.origin)}>abra o acesso local ao Cnutri</a>.</p>}
      <Campo titulo={google ? 'Senha de app do Google (16 caracteres)' : 'Senha SMTP'} ajuda="Vazio mantém a credencial já cadastrada. Ao trocar o servidor ou usuário, cadastre a credencial novamente.">
        <input className={CAMPO} type="password" maxLength={512} autoComplete="new-password" value={form.senha_app}
          disabled={ocupado || !config.protecao_preparada || !config.acesso_seguro} onChange={(e) => alterar('senha_app', e.target.value)}
          placeholder={config.senha_configurada ? 'Credencial já cadastrada' : 'Credencial fornecida pelo serviço de e-mail'} /></Campo>
      <p className="text-xs text-slate-700">A credencial é armazenada de forma criptografada e não é exibida após o cadastro. As exigências de autenticação dependem do provedor.</p>
    </> : <p className="rounded-xl bg-brand-soft p-4 text-sm text-brand-ink">Este modo utiliza o relay autorizado pela TI e dispensa usuário e senha. O serviço precisa permitir o IP de saída e o remetente da unidade.</p>}
    <label className="flex items-start gap-3 text-sm font-semibold"><input type="checkbox" className="mt-1" checked={form.habilitado} disabled={ocupado}
      onChange={(e) => alterar('habilitado', e.target.checked)} />Ativar os avisos desta unidade</label>
    <div className="flex flex-wrap gap-3"><button disabled={ocupado} className={PRIMARIO}>Salvar configuração</button>
      <button type="button" disabled={ocupado} className={SECUNDARIO} onClick={() => { if (formulario.current.reportValidity()) testar() }}>{mudou ? 'Salvar e testar conexão' : 'Testar conexão'}</button></div>
    <p className="text-xs text-slate-700">O teste verifica a conexão e, quando configurada, a autenticação. A autorização do remetente e a entrega são verificadas durante um envio real.</p>
  </form>
}
