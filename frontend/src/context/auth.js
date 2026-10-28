import { createContext, useContext } from 'react'
import { caminhoCozinha, unidadeDoPainel } from '../services/rotasUnidades.js'

export const AuthContext = createContext(null)

export function useAuth() {
  return useContext(AuthContext)
}

export function inicioDoUsuario(usuario) {
  if (usuario?.troca_senha_obrigatoria) return '/senha'
  if (usuario?.perfil === 'ADMIN_TI') return '/admin'
  if (usuario?.perfil === 'NUTRICIONISTA') return '/gestao'
  const filial = usuario?.filiais?.find((f) => f.ativa)
  return filial ? usuario?.perfil === 'COPEIRA' ? `/entregas/${filial.id}` : caminhoCozinha(filial) : '/sem-unidades'
}

export function podeOperar(usuario, filialId, perfis) {
  return Boolean(usuario && !usuario.troca_senha_obrigatoria && perfis.includes(usuario.perfil)
    && (usuario.perfil === 'ADMIN_TI' || usuario.filiais?.some((f) => f.ativa && f.id === Number(filialId))))
}

export function destinoAposLogin(usuario, parametros) {
  const retorno = parametros.get('retorno') || (usuario.perfil === 'COPEIRA' && parametros.get('unidade') ? `/entregas/${parametros.get('unidade')}` : '')
  if (retorno === '/receber') return usuario.troca_senha_obrigatoria ? '/senha?retorno=%2Freceber' : '/receber'
  const partes = retorno.match(/^\/(cozinha|entregas)\/([a-z0-9]+(?:-[a-z0-9]+)*)$/)
  const filial = partes && unidadeDoPainel(retorno, usuario.filiais || [])
  const perfis = partes?.[1] === 'cozinha' ? ['ADMIN_TI', 'NUTRICIONISTA', 'COZINHA'] : ['ADMIN_TI', 'NUTRICIONISTA', 'COPEIRA']
  const referenciaValida = partes && partes[2].length <= 50 && (partes[1] === 'cozinha' && !/^\d+$/.test(partes[2]) || /^[1-9]\d*$/.test(partes[2]))
  const permitido = referenciaValida && (filial || usuario.perfil === 'ADMIN_TI') && podeOperar({ ...usuario, troca_senha_obrigatoria: false }, filial?.id, perfis)
  const volta = permitido ? partes[1] === 'cozinha' && filial ? caminhoCozinha(filial) : retorno : ''
  const destino = volta || inicioDoUsuario({ ...usuario, troca_senha_obrigatoria: false })
  return usuario.troca_senha_obrigatoria ? `/senha?retorno=${encodeURIComponent(volta)}` : destino
}
