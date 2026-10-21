import { Routes, Route } from 'react-router-dom'
import Kiosk from './pages/Kiosk.jsx'
import Cozinha from './pages/Cozinha.jsx'
import Entregas from './pages/Entregas.jsx'
import Login from './pages/Login.jsx'
import Senha from './pages/Senha.jsx'
import Gestao from './pages/Gestao.jsx'
import Admin from './pages/Admin.jsx'
import { AuthProvider, RotaProtegida, SemUnidades } from './context/AuthContext.jsx'

export default function App() {
  return (
    <AuthProvider><Routes>
      <Route path="/:slug" element={<Kiosk />} />
      <Route path="/cozinha/:filialId" element={<Cozinha />} />
      <Route path="/entregas/:filialId" element={<Entregas />} />
      <Route path="/login" element={<Login />} />
      <Route path="/senha" element={<RotaProtegida permitirTrocaSenha><Senha /></RotaProtegida>} />
      <Route path="/gestao" element={<RotaProtegida perfis={['ADMIN_TI', 'NUTRICIONISTA']}><Gestao /></RotaProtegida>} />
      <Route path="/admin" element={<RotaProtegida perfis={['ADMIN_TI']}><Admin /></RotaProtegida>} />
      <Route path="/sem-unidades" element={<RotaProtegida><SemUnidades /></RotaProtegida>} />
      <Route path="*" element={<Kiosk slugPadrao="unidade-centro" />} />
    </Routes></AuthProvider>
  )
}
