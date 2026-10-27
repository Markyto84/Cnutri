import axios from 'axios'

export const recebimentoApi = axios.create({ baseURL: '/api/recebimentos', timeout: 15000 })
export const codigoRecebimentoValido = (codigo) => /^[A-Za-z0-9_-]{43}$/.test(codigo)
export function nomeRecebedorValido(nome) {
  const valor = nome.normalize('NFKC').trim().replace(/ +/g, ' ')
  return nome.length <= 120 && valor.length >= 3 && valor.length <= 120 && /^[\p{L}][\p{L}\p{M} '’.-]*$/u.test(valor)
    && (valor.match(/\p{L}/gu) || []).length >= 2
}
export function registroRecebimentoValido(registro) {
  const valor = registro.normalize('NFKC').trim().toUpperCase()
  return /^[A-Z0-9][A-Z0-9 ./-]{2,49}$/.test(valor) && /[0-9]/.test(valor)
}
