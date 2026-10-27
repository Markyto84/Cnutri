import axios from 'axios'

// A seleção da unidade também funciona sem sessão e com credenciais pessoais antigas.
export const unidadesPublicasApi = axios.create({ baseURL: '/api/operacao' })
