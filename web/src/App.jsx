import { useEffect } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import VectorField from './components/VectorField.jsx';
import { SiteFooter, SiteHeader } from './components/Shell.jsx';
import { useHealth } from './lib/hooks.js';
import Home from './pages/Home.jsx';
import Results from './pages/Results.jsx';
import ResultDetail from './pages/ResultDetail.jsx';
import AdminLayout from './pages/admin/AdminLayout.jsx';
import Dashboard from './pages/admin/Dashboard.jsx';
import Cases from './pages/admin/Cases.jsx';
import Datasets from './pages/admin/Datasets.jsx';
import Models from './pages/admin/Models.jsx';

export default function App() {
  const { pathname } = useLocation();
  const health = useHealth();
  const admin = pathname.startsWith('/admin');

  // Cada página empieza arriba; los filtros cambian la consulta, no la ruta.
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);

  return (
    <>
      {/* En las páginas de lectura el fondo baja de intensidad para no competir con el texto. */}
      <VectorField dim={pathname !== '/'} />
      <div className="scanlines" aria-hidden="true" />
      <div className={`app${admin ? ' admin' : ''}`}>
        <SiteHeader health={health} />
        <main>
          <Routes>
            <Route path="/" element={<Home health={health} />} />
            <Route path="/resultados" element={<Results />} />
            <Route path="/resultados/:id" element={<ResultDetail />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Dashboard health={health} />} />
              <Route path="casos" element={<Cases />} />
              <Route path="datasets" element={<Datasets />} />
              <Route path="modelos" element={<Models />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <SiteFooter />
      </div>
    </>
  );
}
