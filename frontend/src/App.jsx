import { Routes, Route } from 'react-router-dom'
import Kiosk from './pages/Kiosk.jsx'
import Cozinha from './pages/Cozinha.jsx'
import Login from './pages/Login.jsx'
import Gestao from './pages/Gestao.jsx'
import Admin from './pages/Admin.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/:slug" element={<Kiosk />} />
      <Route path="/cozinha/:filialId" element={<Cozinha />} />
      <Route path="/login" element={<Login />} />
      <Route path="/gestao" element={<Gestao />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="*" element={<Kiosk slugPadrao="unidade-centro" />} />
    </Routes>
  )
}
