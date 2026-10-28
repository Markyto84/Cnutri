import axios from 'axios'

export const recebimentoApi = axios.create({ baseURL: '/api/recebimentos', timeout: 15000 })
export const codigoRecebimentoValido = (codigo) => /^[A-Za-z0-9_-]{43}$/.test(codigo)
const CHAVE_RETORNO_QR = 'cnutri-retorno-qr'

export function guardarCodigoRecebimento(codigo, armazenamento = sessionStorage) {
  if (codigoRecebimentoValido(codigo)) armazenamento.setItem(CHAVE_RETORNO_QR, codigo)
}

export function recuperarCodigoRecebimento(armazenamento = sessionStorage) {
  const codigo = armazenamento.getItem(CHAVE_RETORNO_QR) || ''
  return codigoRecebimentoValido(codigo) ? codigo : ''
}

export function limparCodigoRecebimento(armazenamento = sessionStorage) {
  armazenamento.removeItem(CHAVE_RETORNO_QR)
}
export function nomeRecebedorValido(nome) {
  const valor = nome.normalize('NFKC').trim().replace(/ +/g, ' ')
  return nome.length <= 120 && valor.length >= 3 && valor.length <= 120 && /^[\p{L}][\p{L}\p{M} '’.-]*$/u.test(valor)
    && (valor.match(/\p{L}/gu) || []).length >= 2
}
export function registroRecebimentoValido(registro) {
  const valor = registro.normalize('NFKC').trim().toUpperCase()
  return /^[A-Z0-9][A-Z0-9 ./-]{2,49}$/.test(valor) && /[0-9]/.test(valor)
}
