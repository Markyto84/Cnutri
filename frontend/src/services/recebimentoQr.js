import axios from 'axios'

export const recebimentoApi = axios.create({ baseURL: '/api/recebimentos', timeout: 15000 })
export const codigoRecebimentoValido = (codigo) => /^[A-Za-z0-9_-]{43}$/.test(codigo)
export function registroRecebimentoValido(registro) {
  const valor = registro.normalize('NFKC').trim().toUpperCase()
  return /^[A-Z0-9][A-Z0-9 ./-]{2,49}$/.test(valor) && /[0-9]/.test(valor)
}
