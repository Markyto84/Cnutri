import { atrasoPedido } from '../services/painelOperacional.js'

export default function AlertaDemora({ pedido, limites, agora }) {
  const atraso = atrasoPedido(pedido, limites, agora)
  if (!atraso) return null
  return <p className="mt-3 rounded-lg border-l-4 border-amber-600 bg-amber-50 p-3 text-sm text-amber-950">
    <strong>{atraso.etapa} acima do prazo</strong><span className="block">{atraso.minutos} min decorridos · limite: {atraso.limite} min</span>
  </p>
}
