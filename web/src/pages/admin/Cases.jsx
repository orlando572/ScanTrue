import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Fragments, Source, Spectrum, StatusTags, Verdict } from '../../components/Analysis.jsx';
import Filters from '../../components/Filters.jsx';
import { Empty, ErrorState, Loader } from '../../components/ui.jsx';
import { adminApi, query } from '../../lib/api.js';
import { activeCount, emptyFilters, readFilters, toApiQuery, writeFilters } from '../../lib/filters.js';
import { useLoad } from '../../lib/hooks.js';
import { formatDate, presentAnalysis } from '../../lib/presentation.js';
import { ModelPanel, WebPanel } from '../ResultDetail.jsx';

const PAGE = 20;
const REVIEW_TAGS = {
  aprobado: { tag: 'tag--ok', label: 'Aprobado' },
  corregido: { tag: 'tag--acid', label: 'Corregido' },
  descartado: { tag: '', label: 'Descartado' },
};

function ReviewTag({ review }) {
  const state = review ? REVIEW_TAGS[review.decision] : { tag: 'tag--accent', label: 'Pendiente' };
  return <span className={`tag ${state.tag}`}>{state.label}{review?.etiqueta_final ? ` · ${review.etiqueta_final}` : ''}</span>;
}

function CaseRow({ item, current, onSelect }) {
  const view = presentAnalysis(item);
  return (
    <li>
      <button type="button" className={`case-row tone-${view.tone}`} aria-current={current} onClick={() => onSelect(item.id)}>
        <span>
          <span className="preview">{view.fragments[0]?.text ?? 'Sin texto'}</span>
          <span className="chips" style={{ marginTop: 8 }}>
            <ReviewTag review={item.revision} />
            {item.comparacion === 'discrepan' && <span className="tag tag--warn">Discrepan</span>}
            {item.oculto && <span className="tag tag--fail">Oculto</span>}
          </span>
        </span>
        <span className="side">
          <span>{view.level ? `${view.level.value} %` : '—'}</span>
          <span className="label">{view.domain ?? 'sin origen'}</span>
        </span>
      </button>
    </li>
  );
}

// Detalle de un caso con el formulario de revisión (incremento 3).
function CaseDetail({ id, onChange, onDecided }) {
  const { data, error, loading, reload, setData } = useLoad((signal) => adminApi(`/admin/casos/${id}`, { signal }), [id]);
  const [note, setNote] = useState('');
  const [evidence, setEvidence] = useState('');
  const [event, setEvent] = useState('');
  const [action, setAction] = useState({ busy: false, error: null });
  const decideRef = useRef(null);

  useEffect(() => {
    setNote(data?.revision?.nota ?? '');
    setEvidence((data?.revision?.evidencia ?? []).join('\n'));
    setEvent(data?.revision?.grupo_evento ?? '');
    setAction({ busy: false, error: null });
  }, [data?.id, data?.revision?.fecha]);

  async function run(request, decided = false) {
    if (action.busy) return;
    setAction({ busy: true, error: null });
    try {
      const updated = await request();
      setData(updated);
      onChange(updated);
      setAction({ busy: false, error: null });
      if (decided) onDecided(updated.id);
    } catch (failure) { setAction({ busy: false, error: failure }); }
  }

  // «Falsa» o «Real» es la etiqueta final: si coincide con el modelo se aprueba; si no, se corrige.
  function decide(label) {
    if (!data) return;
    const decision = label === null ? 'descartado' : label === data.etiqueta_modelo ? 'aprobado' : 'corregido';
    run(() => adminApi(`/admin/casos/${id}/revision`, {
      method: 'PUT',
      body: {
        decision,
        etiqueta_final: decision === 'corregido' ? label : null,
        nota: note.trim() || null,
        evidencia: evidence.split('\n').map((line) => line.trim()).filter(Boolean).slice(0, 10),
        grupo_evento: event.trim() || null,
      },
    }), true);
  }
  decideRef.current = decide;

  // Atajos: A aprueba la etiqueta del modelo, F falsa, R real, D descarta.
  useEffect(() => {
    function onKey(keyEvent) {
      if (keyEvent.ctrlKey || keyEvent.metaKey || keyEvent.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(keyEvent.target.tagName)) return;
      const key = keyEvent.key.toLowerCase();
      const model = data?.etiqueta_modelo;
      if (key === 'a' && model) decideRef.current(model);
      else if (key === 'f') decideRef.current('falsa');
      else if (key === 'r') decideRef.current('real');
      else if (key === 'd') decideRef.current(null);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [data?.etiqueta_modelo]);

  if (loading) return <div className="panel"><Loader code="Abriendo caso" label="Cargando el caso" rows={1} /></div>;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const view = presentAnalysis(data);
  const original = data.texto_original ?? data.texto;
  const model = data.etiqueta_modelo;

  return (
    <div className="stack">
      <section className={`panel panel--tone tone-${view.tone}`}>
        <div className="card-meta">
          <span className="code">ID {view.code}</span>
          <span>{view.date}</span>
          <Source view={view} />
          {view.words && <span>{view.words}</span>}
          <StatusTags view={view} />
          <ReviewTag review={data.revision} />
        </div>
        <div style={{ display: 'grid', gap: 14, marginBottom: 18 }}>
          <Verdict view={view} />
          <Spectrum view={view} />
        </div>
        <Fragments fragments={view.fragments} />
      </section>

      <section className="panel panel--accent">
        <h2 className="h-panel" style={{ margin: '0 0 6px' }}>Revisión</h2>
        <p className="muted" style={{ margin: '0 0 14px', fontSize: 14 }}>
          {model
            ? <>El resultado combinado apunta a <strong style={{ color: 'var(--color-ink)' }}>{model}</strong>. Elige la etiqueta correcta: si coincide se aprueba; si no, se corrige.</>
            : 'Este caso no tiene resultado combinado: indica la etiqueta correcta o descártalo.'}
        </p>
        <div className="decide">
          <button type="button" className="btn btn--tone tone-very-high" disabled={action.busy} onClick={() => decide('falsa')}>
            Falsa <kbd>F</kbd>
          </button>
          <button type="button" className="btn btn--tone tone-very-low" disabled={action.busy} onClick={() => decide('real')}>
            Real <kbd>R</kbd>
          </button>
          <button type="button" className="btn btn--ghost" disabled={action.busy} onClick={() => decide(null)}>
            Descartar <kbd>D</kbd>
          </button>
        </div>
        <p className="label" style={{ margin: '10px 0 16px' }}>
          {model ? <><kbd>A</kbd> aprueba «{model}» · </> : null}<kbd>J</kbd> <kbd>K</kbd> siguiente y anterior
        </p>
        <div style={{ display: 'grid', gap: 12 }}>
          <label className="field">
            <span>Nota (opcional)</span>
            <textarea className="input" rows={2} maxLength={2000} value={note} onChange={(inputEvent) => setNote(inputEvent.target.value)} placeholder="Por qué se aprueba, corrige o descarta" />
          </label>
          <label className="field">
            <span>Evidencia: un enlace por línea (opcional)</span>
            <textarea className="input" rows={2} value={evidence} onChange={(inputEvent) => setEvidence(inputEvent.target.value)} placeholder="https://…" />
          </label>
          <label className="field">
            <span>Grupo de evento (opcional)</span>
            <input className="input" maxLength={120} value={event} onChange={(inputEvent) => setEvent(inputEvent.target.value)} placeholder="Mismo nombre para noticias del mismo hecho" />
          </label>
        </div>
        {action.error && <p className="alert" style={{ margin: '14px 0 0' }} role="alert">{action.error.message}</p>}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 16 }}>
          {data.revision && (
            <button type="button" className="text-link" disabled={action.busy} onClick={() => run(() => adminApi(`/admin/casos/${id}/revision`, { method: 'DELETE' }))}>
              Quitar la revisión
            </button>
          )}
          <button type="button" className="text-link" disabled={action.busy} onClick={() => run(() => adminApi(`/admin/casos/${id}`, { method: 'PATCH', body: { oculto: !data.oculto } }))}>
            {data.oculto ? 'Volver a mostrar en la web' : 'Ocultar de la web pública'}
          </button>
        </div>
        {data.revision?.fecha && <p className="label" style={{ margin: '12px 0 0' }}>Revisado el {formatDate(data.revision.fecha)}</p>}
      </section>

      <div className="grid-3">
        {view.models.map((item) => (
          <ModelPanel key={item.key} model={item} output={data.resultados?.[item.key]} original={original} />
        ))}
        <WebPanel verification={view.verification} />
      </div>
    </div>
  );
}

export default function Cases() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = readFilters(searchParams, 'admin');
  const key = writeFilters(filters, 'admin').toString();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(null);
  const [selected, setSelected] = useState(null);
  const [more, setMore] = useState({ loading: false, error: null });
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const summary = useLoad((signal) => adminApi('/admin/resumen', { signal }), []);
  const first = useLoad(
    (signal) => adminApi(`/admin/casos${query({ ...toApiQuery(filters, 'admin'), limit: PAGE })}`, { signal }),
    [key],
  );

  useEffect(() => {
    if (!first.data) return;
    setItems(first.data.elementos);
    setTotal(first.data.total);
    setSelected((current) => (first.data.elementos.some((item) => item.id === current) ? current : first.data.elementos[0]?.id ?? null));
    setMore({ loading: false, error: null });
  }, [first.data]);

  async function loadMore() {
    setMore({ loading: true, error: null });
    try {
      const page = await adminApi(`/admin/casos${query({ ...toApiQuery(filters, 'admin'), limit: PAGE, offset: items.length })}`);
      setItems((previous) => {
        const seen = new Set(previous.map((item) => item.id));
        return [...previous, ...page.elementos.filter((item) => !seen.has(item.id))];
      });
      setTotal(page.total);
      setMore({ loading: false, error: null });
    } catch (error) { setMore({ loading: false, error }); }
  }

  const move = (from, step) => {
    const list = itemsRef.current;
    const index = list.findIndex((item) => item.id === from);
    const next = list[index + step];
    if (next) setSelected(next.id);
  };

  // J y K recorren la lista.
  useEffect(() => {
    function onKey(event) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
      const key = event.key.toLowerCase();
      if (key === 'j') move(selected, 1);
      else if (key === 'k') move(selected, -1);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  // Tras revisar o cambiar la visibilidad, la fila de la lista refleja el caso actualizado.
  const update = (updated) => setItems((previous) => previous.map((item) => (
    item.id === updated.id ? { ...item, revision: updated.revision, oculto: updated.oculto } : item
  )));

  const change = (next) => setSearchParams(writeFilters(next, 'admin'), { replace: true });
  const filtered = activeCount(filters, 'admin') > 0;

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Casos y revisión</h1>
        <span className="label" role="status">
          {first.loading ? 'Buscando…' : total == null ? '' : `${total.toLocaleString('es-PE')} casos${filtered ? ' con estos filtros' : ''}`}
        </span>
      </div>
      <Filters filters={filters} onChange={change} domains={summary.data?.dominios ?? []} scope="admin" />

      {first.error ? <ErrorState error={first.error} onRetry={first.reload} />
        : first.loading ? <Loader code="Recuperando casos" label="Cargando casos" />
          : items.length === 0 ? (
            <Empty title={filtered ? 'Ningún caso coincide' : 'Todavía no hay casos'}>
              {filtered
                ? <button type="button" className="btn btn--ghost" onClick={() => change(emptyFilters('admin'))}>Limpiar filtros</button>
                : <p style={{ margin: 0 }}>Los análisis hechos con la extensión aparecerán aquí para revisarlos.</p>}
            </Empty>
          ) : (
            <div className="cases">
              <div>
                <ul className="case-list">
                  {items.map((item) => <CaseRow key={item.id} item={item} current={item.id === selected} onSelect={setSelected} />)}
                </ul>
                {more.error && <div style={{ marginTop: 10 }}><ErrorState error={more.error} /></div>}
                {total != null && items.length < total && (
                  <button type="button" className="btn btn--ghost" style={{ width: '100%', marginTop: 10 }} onClick={loadMore} disabled={more.loading}>
                    {more.loading ? 'Cargando…' : `Cargar más · ${items.length} de ${total}`}
                  </button>
                )}
              </div>
              <div className="case-detail">
                {selected && <CaseDetail key={selected} id={selected} onChange={update} onDecided={(id) => move(id, 1)} />}
              </div>
            </div>
          )}
    </div>
  );
}
