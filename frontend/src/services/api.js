import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      const tokenAtual = localStorage.getItem('token')
      const tokenEnviado = err.config?.headers?.Authorization
      if (!tokenAtual || tokenEnviado === `Bearer ${tokenAtual}`) {
        localStorage.removeItem('token')
        localStorage.removeItem('perfil')
        localStorage.removeItem('nome')
        if (!err.config?.ignorarRedirecionamento401 && !window.location.pathname.startsWith('/login')) window.location.href = '/login'
      }
    }
    throw err
  }
)
