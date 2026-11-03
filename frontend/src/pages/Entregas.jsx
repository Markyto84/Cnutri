import { Link } from 'react-router-dom'
import { MarcaAplicacao } from '../components/Identidade.jsx'

export default function Entregas() {
  return <main className="auth-shell"><section className="receipt-card space-y-5">
    <MarcaAplicacao compacto />
    <h1>Entregas das copeiras desativadas</h1>
    <p>A entrega é comprovada pela assinatura manual na filipeta. Preencha o nome do recebedor, a assinatura, a data e a hora no papel.</p>
    <p>A Nutrição deve escanear o QR Code da filipeta para registrar os dados e anexar a foto do comprovante.</p>
    <Link to="/login" className="ui-button ui-button-primary w-full">Acessar o sistema</Link>
  </section></main>
}