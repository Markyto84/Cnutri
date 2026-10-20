import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)

export function useAuth() {
  return useContext(AuthContext)
}

export function inicioDoUsuario(usuario) {
  if (usuario?.perfil === 'ADMIN_TI') return '/admin'
  if (usuario?.perfil === 'NUTRICIONISTA') return '/gestao'
  const filial = usuario?.filiais?.find((f) => f.ativa)
  return filial ? `/${usuario?.perfil === 'COPEIRA' ? 'entregas' : 'cozinha'}/${filial.id}` : '/sem-unidades'
}
