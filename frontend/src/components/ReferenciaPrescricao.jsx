const CAMPO = 'mt-1 min-h-12 w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-base font-normal'

export default function ReferenciaPrescricao({ valor, onChange }) {
  function alterar(chave, texto) { onChange({ ...valor, [chave]: texto }) }
  return <fieldset className="min-w-0 space-y-4 rounded-xl border border-brand/30 bg-brand-soft p-4">
    <legend className="px-1 font-bold text-brand-ink">Prescrição vigente do paciente</legend>
    <p className="text-sm text-slate-800">Informe os dados da prescrição existente no prontuário. A gestão poderá registrar a conferência deste vínculo.</p>
    <label className="block text-sm font-semibold">Referência da prescrição / atendimento *
      <input required maxLength={150} value={valor.referencia || ''} onChange={(e) => alterar('referencia', e.target.value)} className={CAMPO}
        placeholder="Identificação que permita localizar a prescrição no prontuário" /></label>
    <label className="block text-sm font-semibold">Data e hora da prescrição (Brasília) *
      <input required type="datetime-local" step="1" value={valor.data_hora || ''} onChange={(e) => alterar('data_hora', e.target.value)} className={CAMPO} /></label>
    <label className="block text-sm font-semibold">Nome do profissional prescritor *
      <input required minLength={3} maxLength={100} value={valor.prescritor_nome || ''} onChange={(e) => alterar('prescritor_nome', e.target.value)} className={CAMPO} /></label>
    <label className="block text-sm font-semibold">Conselho, região/UF e registro do prescritor *
      <input required minLength={3} maxLength={100} value={valor.prescritor_registro || ''} onChange={(e) => alterar('prescritor_registro', e.target.value)} className={CAMPO}
        placeholder="Ex.: CRN-3 nº … ou CRM-SP nº …" /></label>
  </fieldset>
}
