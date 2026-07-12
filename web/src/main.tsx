import './lib/headless-raf' // must evaluate before maplibre-gl (binds native rAF at module eval)
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import MethodsPage from './pages/MethodsPage.tsx'
import StatusPage from './pages/StatusPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/map" replace />} />
        <Route path="/map" element={<App />} />
        <Route path="/property/:apn" element={<App />} />
        <Route path="/methods" element={<MethodsPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="*" element={<Navigate to="/map" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
