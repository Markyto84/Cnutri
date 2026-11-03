const MAX_ARQUIVO = 12 * 1024 * 1024
const MAX_LADO = 2000

// O formulário usa explicitamente o horário de Brasília, independentemente do dispositivo.
export function dataEntregaISO(valor) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(valor)) return ''
  const data = new Date(`${valor}:00-03:00`)
  if (!Number.isFinite(data.getTime())) return ''
  const local = new Date(data.getTime() - 3 * 60 * 60 * 1000).toISOString().slice(0, 16)
  return local === valor ? `${valor}:00-03:00` : ''
}

export function agoraBrasilia(agora = new Date()) {
  return new Date(agora.getTime() - 3 * 60 * 60 * 1000).toISOString().slice(0, 16)
}

export async function prepararFotoComprovante(arquivo) {
  if (!arquivo || !arquivo.size || arquivo.size > MAX_ARQUIVO) throw new Error('Selecione uma foto de até 12 MB.')
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(arquivo.type)) throw new Error('Use uma foto JPG, PNG ou WebP. No celular, escolha o formato mais compatível da câmera.')
  let imagem
  try {
    imagem = await createImageBitmap(arquivo)
    if (Math.min(imagem.width, imagem.height) < 240 || Math.max(imagem.width, imagem.height) < 600) throw new Error('A foto está pequena demais. Fotografe a filipeta novamente.')
    const escala = Math.min(1, MAX_LADO / Math.max(imagem.width, imagem.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(imagem.width * escala)
    canvas.height = Math.round(imagem.height * escala)
    const contexto = canvas.getContext('2d')
    if (!contexto) throw new Error('Não foi possível preparar a foto neste navegador.')
    contexto.fillStyle = '#fff'
    contexto.fillRect(0, 0, canvas.width, canvas.height)
    contexto.drawImage(imagem, 0, 0, canvas.width, canvas.height)
    const foto = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (!foto) throw new Error('Não foi possível preparar a foto. Tente fotografar novamente.')
    return foto
  } catch (erro) {
    if (erro instanceof Error && !['InvalidStateError', 'EncodingError'].includes(erro.name)) throw erro
    throw new Error('Não foi possível abrir a foto. Use JPG, PNG ou WebP e tente novamente.')
  } finally { imagem?.close() }
}
