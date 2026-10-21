import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)

export function useAuth() {
  return useContext(AuthContext)
}

export function inicioDoUsuario(usuario) {
  if (usuario?.troca_senha_obrigatoria) return '/senha'
  if (usuario?.perfil === 'ADMIN_TI') return '/admin'
  if (usuario?.perfil === 'NUTRICIONISTA') return '/gestao'
  const filial = usuario?.filiais?.find((f) => f.ativa)
  return filial ? `/${usuario?.perfil === 'COPEIRA' ? 'entregas' : 'cozinha'}/${filial.id}` : '/sem-unidades'
}

export function podeOperar(usuario, filialId, perfis) {
  return Boolean(usuario && !usuario.troca_senha_obrigatoria && perfis.includes(usuario.perfil)
    && (usuario.perfil === 'ADMIN_TI' || usuario.filiais?.some((f) => f.ativa && f.id === Number(filialId))))
}

export function destinoAposLogin(usuario, parametros) {
  const retorno = parametros.get('retorno') || (usuario.perfil === 'COPEIRA' && parametros.get('unidade') ? `/entregas/${parametros.get('unidade')}` : '')
  const partes = retorno.match(/^\/(cozinha|entregas)\/([1-9]\d*)$/)
  const perfis = partes?.[1] === 'cozinha' ? ['ADMIN_TI', 'NUTRICIONISTA', 'COZINHA'] : ['ADMIN_TI', 'NUTRICIONISTA', 'COPEIRA']
  const permitido = partes && podeOperar({ ...usuario, troca_senha_obrigatoria: false }, partes[2], perfis)
  const destino = permitido ? retorno : inicioDoUsuario({ ...usuario, troca_senha_obrigatoria: false })
  return usuario.troca_senha_obrigatoria ? `/senha?retorno=${encodeURIComponent(permitido ? retorno : '')}` : destino
}
