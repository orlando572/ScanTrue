import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ResultCard } from '../components/Analysis.jsx';
import Filters from '../components/Filters.jsx';
import { Empty, ErrorState, Loader, Sweep } from '../components/ui.jsx';
import { publicApi, query } from '../lib/api.js';
import { activeCount, emptyFilters, readFilters, toApiQuery, writeFilters } from '../lib/filters.js';
import { useLoad } from '../lib/hooks.js';
import { presentAnalysis } from '../lib/presentation.js';

const PAGE = 12;

export default function Results() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = readFilters(searchParams);
  const key = writeFilters(filters).toString();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(null);
  const [more, setMore] = useState({ loading: false, error: null });

  const summary = useLoad((signal) => publicApi('/publico/resumen', { signal }), []);
  const first = useLoad(
    (signal) => publicApi(`/publico/analisis${query({ ...toApiQuery(filters), limit: PAGE })}`, { signal }),
    [key],
  );

  useEffect(() => {
    if (first.data) { setItems(first.data.elementos); setTotal(first.data.total); }
    setMore({ loading: false, error: null });
  }, [first.data]);

  async function loadMore() {
    setMore({ loading: true, error: null });
    try {
      const page = await publicApi(`/publico/analisis${query({ ...toApiQuery(filters), limit: PAGE, offset: items.length })}`);
      setItems((previous) => {
        const seen = new Set(previous.map((item) => item.id));
        return [...previous, ...page.elementos.filter((item) => !seen.has(item.id))];
      });
      setTotal(page.total);
      setMore({ loading: false, error: null });
    } catch (error) { setMore({ loading: false, error }); }
  }

  const change = (next) => setSearchParams(writeFilters(next), { replace: true });
  const filtered = activeCount(filters) > 0;
  const shown = first.loading ? [] : items;

  return (
    <div className="shell">
      <header className="page-head">
        <span className="label label--accent">Registro público</span>
        <h1 className="display h-page" style={{ margin: '8px 0 10px' }}>Resultados</h1>
        <p className="muted" style={{ margin: 0, maxWidth: 680 }}>
          Todos los fragmentos analizados con ScanTrue y lo que respondió cada modelo. No se muestra quién
          hizo cada análisis. Las salidas son una orientación: no verifican los hechos.
        </p>
      </header>

      <Filters filters={filters} onChange={change} domains={summary.data?.dominios ?? []} />

      <div className="results-bar">
        <span className="label" role="status">
          {first.loading ? 'Buscando…' : total == null ? '' : `${total.toLocaleString('es-PE')} análisis${filtered ? ' con estos filtros' : ''}`}
        </span>
      </div>

      {first.error ? <ErrorState error={first.error} onRetry={first.reload} />
        : first.loading ? <Loader code="Recuperando registros" label="Cargando resultados" />
          : shown.length === 0 ? (
            <Empty title={filtered ? 'Nada coincide con estos filtros' : 'Todavía no hay análisis'}>
              {filtered
                ? <><p style={{ margin: '0 0 12px' }}>Prueba con otra búsqueda o quita algún filtro.</p><button type="button" className="btn btn--ghost" onClick={() => change(emptyFilters())}>Limpiar filtros</button></>
                : <p style={{ margin: 0 }}>Cuando alguien analice una noticia con la extensión de ScanTrue, aparecerá aquí.</p>}
            </Empty>
          ) : (
            <>
              <div className="cards boot">
                {shown.map((item) => (
                  <ResultCard key={item.id} view={presentAnalysis(item)} to={`/resultados/${item.id}`} />
                ))}
              </div>
              {more.error && <div style={{ marginTop: 14 }}><ErrorState error={more.error} /></div>}
              {total != null && shown.length < total && (
                <div style={{ display: 'grid', justifyItems: 'center', gap: 10, marginTop: 22 }}>
                  <button type="button" className="btn btn--ghost" onClick={loadMore} disabled={more.loading}>
                    {more.loading ? 'Cargando…' : `Cargar más · ${shown.length} de ${total}`}
                  </button>
                  {more.loading && <Sweep />}
                </div>
              )}
            </>
          )}
    </div>
  );
}
