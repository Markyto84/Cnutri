import axios from 'axios'

// O solicitante é informado no formulário; a sessão pessoal não participa deste fluxo.
export const kioskApi = axios.create({ baseURL: '/api/public' })
