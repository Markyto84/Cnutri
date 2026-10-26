// Adaptador mantido para componentes que ainda utilizam o nome anterior.
import { Assinatura } from '../modules/assinatura/index.js'

export default function AssinaturaRecebedor(props) {
  return <Assinatura rotulo="Área de assinatura do recebedor" {...props} />
}
