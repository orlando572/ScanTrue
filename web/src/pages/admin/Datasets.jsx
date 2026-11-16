import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Empty, ErrorState, Icon, Loader } from '../../components/ui.jsx';
import { adminApi, adminDownload, query } from '../../lib/api.js';
import { useLoad } from '../../lib/hooks.js';
import { DATASET_CUTS, DATASET_EXCLUDED, formatDate, percent, shortId } from '../../lib/presentation.js';

const PAGE = 25;

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Por debajo de esto por clase, las métricas de la prueba del panel varían demasiado.
const MIN_TEST_PER_CLASS = 20;

const sum = (values) => Object.values(values ?? {}).reduce((total, value) => total + value, 0);

// Qué entra en una versión y qué se separó: duplicados, conflictos, estándar, grupos y particiones.
function Summary({ summary }) {
  const split = summary.por_particion_etiqueta ?? {};
  const cell = (partition, label) => split[partition]?.[label] ?? 0;
  const standard = summary.estandar ?? {};
  const excluded = Object.entries(summary.excluidas ?? {}).filter(([, count]) => count);
  const cuts = Object.entries(summary.recortes ?? {}).filter(([, count]) => count);
  const crosses = summary.cruces_comun ?? {};
  const dropped = summary.excluidas_casos ?? [];
  const testFalse = cell('prueba', 'falsa');
  const testReal = cell('prueba', 'real');
  return (
    <>
      <div className="tiles">
        <div className="tile"><span className="label">Casos</span><b style={{ color: 'var(--color-acid)' }}>{summary.casos}</b><small>de {summary.candidatos} aprobados o corregidos</small></div>
        <div className="tile"><span className="label">Duplicados retirados</span><b>{summary.duplicados_retirados}</b><small>copias exactas del mismo texto</small></div>
        <div className="tile"><span className="label">Conflictos retirados</span><b style={{ color: summary.conflictos_retirados ? 'var(--color-false)' : undefined }}>{summary.conflictos_retirados}</b><small>mismo texto con etiquetas contrarias</small></div>
        <div className="tile"><span className="label">Fuera por el estándar</span><b style={{ color: sum(summary.excluidas) ? 'var(--color-false)' : undefined }}>{sum(summary.excluidas)}</b><small>idioma, longitud, oraciones incompletas o prueba congelada</small></div>
        <div className="tile"><span className="label">Fragmentos</span><b>{summary.fragmentos ?? 0}</b><small>{standard.min_tokens ?? 100}–{standard.max_tokens_fragmento ?? 200} palabras, terminados en punto</small></div>
        <div className="tile"><span className="label">Grupos</span><b>{summary.grupos}</b><small>{summary.grupos_con_varios} con varios casos (misma página, evento o casi duplicado)</small></div>
      </div>
      <ul className="muted" style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 14 }}>
        {excluded.map(([key, count]) => <li key={key}>{count} fuera: {DATASET_EXCLUDED[key] ?? key}</li>)}
        {cuts.map(([key, count]) => <li key={key}>{count} {DATASET_CUTS[key] ?? key}</li>)}
        {summary.uniones_casi_duplicado > 0 && <li>{summary.uniones_casi_duplicado} unidas a otra por ser casi la misma noticia</li>}
        {crosses.comprobado
          ? <li>Comparadas con los {crosses.fragmentos_indice} fragmentos de comun_v1: {crosses.en_desarrollo_a_entrenamiento ?? 0} ya estaban en su desarrollo y van a entrenamiento</li>
          : <li>No se pudo comparar con comun_v1 (falta datasets/comun_v1): revisa los cruces antes de entrenar</li>}
      </ul>
      {dropped.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary className="text-link" style={{ cursor: 'pointer' }}>
            Ver {dropped.length === 1 ? 'la noticia que queda fuera' : `las ${dropped.length} noticias que quedan fuera`}
          </summary>
          <ul style={{ margin: '10px 0 0', paddingLeft: 18, display: 'grid', gap: 6, fontSize: 14 }}>
            {dropped.map((item) => (
              <li key={`${item.analisis_id}-${item.motivo}`}>
                <Link className="text-link mono" to={`/admin/casos?caso=${item.analisis_id}`}>{shortId(item.analisis_id)}</Link>
                {' · '}<span className="muted">{DATASET_EXCLUDED[item.motivo] ?? item.motivo}</span>
              </li>
            ))}
          </ul>
          {dropped.length >= 100 && <p className="label" style={{ margin: '8px 0 0' }}>Se muestran las 100 primeras.</p>}
        </details>
      )}
      {Math.min(testFalse, testReal) < MIN_TEST_PER_CLASS && (
        <p className="alert alert--info" style={{ margin: '12px 0 0' }} role="note">
          La prueba tiene {testFalse} {testFalse === 1 ? 'falsa' : 'falsas'} y {testReal} {testReal === 1 ? 'real' : 'reales'}:
          aún no es fiable para comparar modelos. Usa la prueba congelada de comun_v1 como referencia
          hasta tener al menos {MIN_TEST_PER_CLASS} noticias de cada clase en prueba.
        </p>
      )}
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table className="data">
          <thead><tr><th>Partición</th><th>Falsas</th><th>Reales</th><th>Noticias</th><th>Fragmentos</th></tr></thead>
          <tbody>
            {['entrenamiento', 'prueba'].map((partition) => (
              <tr key={partition}>
                <td style={{ textTransform: 'capitalize' }}>{partition}</td>
                <td className="num">{cell(partition, 'falsa')}</td>
                <td className="num">{cell(partition, 'real')}</td>
                <td className="num">{summary.por_particion?.[partition] ?? 0}</td>
                <td className="num">{summary.fragmentos_por_particion?.[partition] ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="label" style={{ margin: '12px 0 0' }}>
        Cada grupo va entero a una partición · prueba ≈ {percent(summary.fraccion_prueba)} de las noticias de cada clase
        {standard.tope_noticia ? ` · máximo ${standard.tope_noticia} palabras por noticia` : ''}
      </p>
    </>
  );
}

function NewVersion({ onCreated }) {
  const [fraction, setFraction] = useState(20);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [state, setState] = useState({ sending: false, error: null });
  const preview = useLoad(
    (signal) => adminApi(`/admin/datasets/vista-previa${query({ fraccion_prueba: fraction / 100 })}`, { signal }),
    [fraction],
  );

  async function submit(event) {
    event.preventDefault();
    setState({ sending: true, error: null });
    try {
      const version = await adminApi('/admin/datasets', {
        method: 'POST',
        body: { nombre: name.trim(), descripcion: description.trim() || null, fraccion_prueba: fraction / 100 },
        timeout: 60_000,
      });
      setName('');
      setDescription('');
      setState({ sending: false, error: null });
      onCreated(version);
    } catch (error) { setState({ sending: false, error }); }
  }

  const ready = preview.data && preview.data.casos > 0;
  return (
    <section className="panel panel--accent">
      <h2 className="h-panel" style={{ margin: '0 0 6px' }}>Nueva versión</h2>
      <p className="muted" style={{ margin: '0 0 16px', fontSize: 14 }}>
        Una versión es una copia fija de los casos aprobados o corregidos hasta hoy, con su etiqueta,
        procedencia y evidencia, guardados con el estándar de comun_v1: cada noticia en fragmentos
        de 100 a 200 palabras que terminan en punto. No cambia aunque después se revisen más casos.
      </p>
      {preview.error ? <ErrorState error={preview.error} onRetry={preview.reload} />
        : !preview.data ? <Loader code="Calculando" label="Calculando la vista previa" rows={1} />
          : ready ? <Summary summary={preview.data} />
            : (
              <div className="alert alert--info">
                Todavía no hay casos aprobados o corregidos. <Link className="text-link" to="/admin/casos?revision=pendiente">Revisar casos</Link>
              </div>
            )}
      <form onSubmit={submit} style={{ display: 'grid', gap: 12, marginTop: 18 }}>
        <div className="filter-grid">
          <label className="field">
            <span>Nombre de la versión</span>
            <input className="input" required maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="revisados_v1" />
          </label>
          <label className="field">
            <span>Parte para prueba · {fraction} %</span>
            <input type="range" min={5} max={50} step={5} value={fraction} onChange={(event) => setFraction(Number(event.target.value))} style={{ accentColor: 'var(--color-coral)', height: 40 }} />
          </label>
        </div>
        <label className="field">
          <span>Descripción (opcional)</span>
          <input className="input" maxLength={500} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Qué incluye o para qué se usará" />
        </label>
        {state.error && <p className="alert" style={{ margin: 0 }} role="alert">{state.error.message}</p>}
        <div><button type="submit" className="btn" disabled={!ready || state.sending}>{state.sending ? 'Creando…' : 'Crear versión'}</button></div>
      </form>
    </section>
  );
}

function Items({ version }) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useLoad(
    (signal) => adminApi(`/admin/datasets/${version.id}${query({ limit: PAGE, offset })}`, { signal }),
    [version.id, offset],
  );
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !data) return <Loader code="Abriendo versión" label="Cargando los casos" rows={1} />;
  const total = data.total ?? data.elementos.length;
  return (
    <>
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Partición</th><th>Etiqueta</th><th>Texto</th><th>Palabras</th><th>Origen</th><th>Decisión</th><th>Grupo</th></tr></thead>
          <tbody>
            {data.elementos.map((item) => (
              <tr key={item.id}>
                <td>{item.particion}</td>
                <td><span className={`tag ${item.etiqueta === 'falsa' ? 'tag--fail' : 'tag--ok'}`}>{item.etiqueta}</span></td>
                <td style={{ minWidth: 280 }}>{item.texto.length > 220 ? `${item.texto.slice(0, 219)}…` : item.texto}</td>
                <td className="num">{item.tokens_bilstm ?? '—'}</td>
                <td className="mono">{item.dominio ?? '—'}</td>
                <td>{item.decision}</td>
                <td className="mono">{shortId(item.grupo.replace('g_', ''))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > PAGE && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 12 }}>
          <button type="button" className="btn btn--ghost btn--small" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Anteriores</button>
          <span className="label">{offset + 1}–{Math.min(offset + PAGE, total)} de {total}</span>
          <button type="button" className="btn btn--ghost btn--small" disabled={offset + PAGE >= total || loading} onClick={() => setOffset(offset + PAGE)}>Siguientes</button>
        </div>
      )}
    </>
  );
}

function Version({ version, open, onToggle, onDeleted }) {
  const [state, setState] = useState({ busy: null, error: null, confirm: false });

  async function run(name, action) {
    setState({ busy: name, error: null, confirm: false });
    try { await action(); setState({ busy: null, error: null, confirm: false }); }
    catch (error) { setState({ busy: null, error, confirm: false }); }
  }

  const csv = () => run('csv', async () => {
    const file = await adminDownload(`/admin/datasets/${version.id}/exportar`);
    save(file.blob, file.name);
  });
  // ZIP con el formato de comun_v1 (fragmentos por partición, procedencia y manifest.json).
  const standard = () => run('zip', async () => {
    const file = await adminDownload(`/admin/datasets/${version.id}/exportar${query({ formato: 'estandar' })}`);
    save(file.blob, file.name);
  });
  // Las versiones anteriores al estándar (una fila por noticia) no tienen fragmentos.
  const hasManifest = Boolean(version.manifiesto?.archivos);
  const hasStandard = hasManifest || (version.resumen?.fragmentos ?? 0) > 0;
  // El manifiesto describe la versión sin los textos: archivos con SHA-256, reglas, código y recuentos.
  const manifest = () => save(
    new Blob([JSON.stringify({
      id: version.id, nombre: version.nombre, descripcion: version.descripcion, fecha: version.fecha,
      ...(hasManifest ? version.manifiesto : {
        resumen: version.resumen,
        reglas: hasStandard
          ? 'Versión con fragmentos creada antes del manifiesto: sin SHA-256 guardados.'
          : 'Versión anterior al estándar: una fila por noticia, sin fragmentos.',
      }),
    }, null, 2)], { type: 'application/json' }),
    `scantrue_${version.nombre.replace(/[^\w.-]+/g, '_')}_manifiesto.json`,
  );
  const remove = () => run('delete', async () => {
    await adminApi(`/admin/datasets/${version.id}`, { method: 'DELETE' });
    onDeleted(version.id);
  });

  const summary = version.resumen;
  return (
    <article className="panel">
      <div className="version-head">
        <div style={{ minWidth: 0 }}>
          <h3 className="h-panel" style={{ margin: 0, color: 'var(--color-acid)' }}>{version.nombre}</h3>
          <span className="label">{formatDate(version.fecha)} · {summary.casos} noticias{hasStandard ? ` · ${summary.fragmentos} fragmentos` : ' · anterior al estándar'} · {summary.por_etiqueta?.falsa ?? 0} falsas · {summary.por_etiqueta?.real ?? 0} reales</span>
          {version.descripcion && <p className="muted" style={{ margin: '8px 0 0' }}>{version.descripcion}</p>}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <button type="button" className="btn btn--small" onClick={csv} disabled={state.busy !== null}>
            <span style={{ width: 14 }}><Icon name="download" /></span>{state.busy === 'csv' ? 'Preparando…' : 'CSV'}
          </button>
          <button type="button" className="btn btn--small" onClick={standard} disabled={state.busy !== null || !hasStandard}
            title={hasStandard ? 'Fragmentos con las columnas de comun_v1, procedencia y manifest.json' : 'Versión anterior al estándar: crea una nueva para exportarla para entrenar'}>
            <span style={{ width: 14 }}><Icon name="download" /></span>{state.busy === 'zip' ? 'Preparando…' : 'Para entrenar (.zip)'}
          </button>
          <button type="button" className="btn btn--ghost btn--small" onClick={manifest}>Manifiesto</button>
          <button type="button" className="btn btn--ghost btn--small" aria-expanded={open} onClick={onToggle}>{open ? 'Cerrar' : 'Ver casos'}</button>
        </div>
      </div>
      {state.error && <p className="alert" style={{ margin: '14px 0 0' }} role="alert">{state.error.message}</p>}
      {open && (
        <div style={{ marginTop: 18 }}>
          <Summary summary={summary} />
          <div style={{ height: 18 }} />
          <Items version={version} />
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, marginTop: 18 }}>
            {state.confirm ? (
              <>
                <span>¿Eliminar «{version.nombre}»? Los casos revisados no se borran.</span>
                <button type="button" className="btn btn--danger btn--small" onClick={remove} disabled={state.busy !== null}>Eliminar versión</button>
                <button type="button" className="btn btn--ghost btn--small" onClick={() => setState({ busy: null, error: null, confirm: false })}>Cancelar</button>
              </>
            ) : <button type="button" className="text-link" style={{ color: 'var(--color-false)' }} onClick={() => setState({ busy: null, error: null, confirm: true })}>Eliminar esta versión</button>}
          </div>
        </div>
      )}
    </article>
  );
}

export default function Datasets() {
  const { data, error, loading, reload, setData } = useLoad((signal) => adminApi('/admin/datasets', { signal }), []);
  const [open, setOpen] = useState(null);

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <h1 className="display h-page" style={{ margin: 0 }}>Versiones de dataset</h1>
      <NewVersion onCreated={(version) => { setData([version, ...(data ?? [])]); setOpen(version.id); }} />
      <h2 className="display" style={{ margin: '8px 0 0', fontSize: 16 }}>Versiones creadas</h2>
      {error ? <ErrorState error={error} onRetry={reload} />
        : loading ? <Loader code="Recuperando versiones" label="Cargando versiones" rows={2} />
          : data.length === 0 ? <Empty title="Aún no hay versiones"><p style={{ margin: 0 }}>Revisa casos y crea la primera versión con el formulario de arriba.</p></Empty>
            : data.map((version) => (
              <Version
                key={version.id} version={version} open={open === version.id}
                onToggle={() => setOpen(open === version.id ? null : version.id)}
                onDeleted={(id) => setData(data.filter((item) => item.id !== id))}
              />
            ))}
    </div>
  );
}
