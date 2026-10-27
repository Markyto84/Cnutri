import axios from 'axios'

// A operação da cozinha independe da sessão pessoal usada na gestão ou nas entregas.
export const cozinhaApi = axios.create({ baseURL: '/api/cozinha' })
