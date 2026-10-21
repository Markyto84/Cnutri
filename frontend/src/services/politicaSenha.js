export const MIN_SENHA = 8
export const MAX_SENHA = 12
export const REGRA_SENHA = 'Use de 8 a 12 caracteres, com pelo menos uma letra maiúscula, um número e um caractere especial.'
export const PADRAO_SENHA = '(?=.*\\p{Lu})(?=.*[0-9])(?=.*[^\\p{L}\\p{N}\\s]).+'

export function senhaValida(senha) {
  return [...senha].length >= MIN_SENHA && [...senha].length <= MAX_SENHA
    && /\p{Lu}/u.test(senha) && /[0-9]/.test(senha) && /[^\p{L}\p{N}\s]/u.test(senha)
}
