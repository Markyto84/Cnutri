import { useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { mensagemErro } from '../services/painelOperacional.js'

export function useConsultaGestao(caminho, parametros, intervalo = 0) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(true)
  const [revisao, setRevisao] = useState(0)
  const chave = JSON.stringify(parametros)
  useEffect(() => {
    const controller = new AbortController()
    let emCurso = false
    async function carregar() {
      if (emCurso) return
      emCurso = true
      try {
        const { data } = await api.get(caminho, { params: JSON.parse(chave), signal: controller.signal })
        if (!controller.signal.aborted) { setDados(data); setErro('') }
      } catch (e) {
        if (!controller.signal.aborted) { setErro(mensagemErro(e)); setDados(null) }
      } finally {
        if (!controller.signal.aborted) setCarregando(false)
        emCurso = false
      }
    }
    const inicial = setTimeout(() => { setCarregando(true); setDados(null); carregar() }, 0)
    const timer = intervalo ? setInterval(carregar, intervalo) : null
    return () => { controller.abort(); clearTimeout(inicial); clearInterval(timer) }
  }, [caminho, chave, revisao, intervalo])
  return { dados, erro, carregando, atualizar: () => setRevisao((r) => r + 1) }
}
