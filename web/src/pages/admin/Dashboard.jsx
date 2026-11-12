import { Link } from 'react-router-dom';
import { ServiceStrip } from '../../components/Shell.jsx';
import { CountUp, ErrorState, Loader } from '../../components/ui.jsx';
import { adminApi } from '../../lib/api.js';
import { LEVELS } from '../../lib/filters.js';
import { useLoad } from '../../lib/hooks.js';
import { percent, share } from '../../lib/presentation.js';

function Tile({ label, value, note, color, suffix = '' }) {
  return (
    <div className="panel panel--tight tile" style={{ '--c': color }}>
      <span className="label">{label}</span>
      <b><CountUp value={value} />{suffix}</b>
      {note && <small>{note}</small>}
    </div>
  );
}

function Bars({ rows, total }) {
  return (
    <ul className="rows">
      {rows.map((row) => (
        <li key={row.label} className={`row-bar${row.tone ? ` tone-${row.tone}` : ''}`} style={{ '--c': row.color ?? (row.tone ? 'var(--tone)' : undefined) }}>
          <span>{row.label}</span>
          <span className="track"><i style={{ width: `${share(row.value, total)}%` }} /></span>
          <span className="n">{row.value}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Dashboard({ health }) {
  const { data, error, loading, reload } = useLoad((signal) => adminApi('/admin/resumen', { signal }), []);
  if (loading) return <div className="page-head"><Loader code="Consultando el registro" label="Cargando el panel" rows={2} /></div>;
  if (error) return <div className="page-head"><ErrorState error={error} onRetry={reload} /></div>;

  const reviews = data.revisiones ?? {};
  const reviewed = (reviews.aprobado ?? 0) + (reviews.corregido ?? 0) + (reviews.descartado ?? 0);
  const peak = Math.max(1, ...data.por_dia.map((day) => day.n));

  return (
    <div className="stack boot" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Panel</h1>
        <ServiceStrip health={health} />
      </div>

      <div className="tiles">
        <Tile label="Análisis" value={data.total} note={`${data.ultimas_24h} en las últimas 24 h`} color="var(--color-acid)" />
        <Tile label="Pendientes de revisión" value={reviews.pendiente ?? 0} note={`${reviews.discrepan_pendientes ?? 0} con modelos que discrepan`} color="var(--color-coral)" />
        <Tile label="Revisados" value={reviewed} note={`${share(reviewed, data.total)} % del total`} />
        <Tile label="Versiones de dataset" value={data.datasets} note={`${(reviews.aprobado ?? 0) + (reviews.corregido ?? 0)} casos aprovechables`} color="var(--color-violet)" />
        <Tile label="Ocultos de la web" value={data.ocultos} note="No aparecen en Resultados" />
      </div>

      {(reviews.discrepan_pendientes ?? 0) > 0 && (
        <div className="alert alert--info" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span>Hay {reviews.discrepan_pendientes} casos pendientes donde BiLSTM y BETO no coinciden: son los que más aportan al dataset.</span>
          <Link className="btn btn--small" to="/admin/casos?revision=pendiente&comparacion=discrepan">Revisarlos</Link>
        </div>
      )}

      <div className="grid-2">
        <section className="panel">
          <h2 className="h-panel" style={{ margin: '0 0 16px' }}>Nivel del resultado</h2>
          <Bars total={data.total} rows={LEVELS.map((level, index) => ({ label: level.short, value: data.niveles[index], tone: level.tone }))} />
          <p className="label" style={{ margin: '16px 0 0' }}>Salida media para falsa · {percent(data.probabilidad_media)}</p>
        </section>

        <section className="panel">
          <h2 className="h-panel" style={{ margin: '0 0 16px' }}>Acuerdo y revisión</h2>
          <Bars total={data.total} rows={[
            { label: 'Coinciden', value: data.comparacion.coinciden ?? 0, color: 'var(--color-real)' },
            { label: 'No coinciden', value: data.comparacion.discrepan ?? 0, color: '#ffb21e' },
            { label: 'Un solo modelo', value: data.comparacion.no_disponible ?? 0, color: 'var(--color-muted)' },
          ]} />
          <div style={{ height: 18 }} />
          <Bars total={data.total} rows={[
            { label: 'Aprobados', value: reviews.aprobado ?? 0, color: 'var(--color-real)' },
            { label: 'Corregidos', value: reviews.corregido ?? 0, color: 'var(--color-acid)' },
            { label: 'Descartados', value: reviews.descartado ?? 0, color: 'var(--color-muted)' },
            { label: 'Pendientes', value: reviews.pendiente ?? 0, color: 'var(--color-coral)' },
          ]} />
        </section>

        <section className="panel">
          <h2 className="h-panel" style={{ margin: '0 0 16px' }}>Análisis por día · 30 días</h2>
          {data.por_dia.length > 0 ? (
            <>
              <div className="days" role="img" aria-label={`Análisis por día en los últimos 30 días; máximo ${peak} en un día`}>
                {data.por_dia.map((day) => <i key={day.dia} title={`${day.dia}: ${day.n}`} style={{ height: `${(day.n / peak) * 100}%` }} />)}
              </div>
              <p className="label" style={{ margin: '10px 0 0', display: 'flex', justifyContent: 'space-between' }}>
                <span>{data.por_dia[0].dia}</span><span>{data.por_dia.at(-1).dia}</span>
              </p>
            </>
          ) : <p className="muted" style={{ margin: 0 }}>Sin análisis en los últimos 30 días.</p>}
        </section>

        <section className="panel">
          <h2 className="h-panel" style={{ margin: '0 0 16px' }}>Páginas de origen</h2>
          {data.dominios.length > 0
            ? <Bars total={Math.max(...data.dominios.map((item) => item.n))} rows={data.dominios.slice(0, 8).map((item) => ({ label: item.dominio, value: item.n }))} />
            : <p className="muted" style={{ margin: 0 }}>Ningún análisis guardó su página de origen.</p>}
        </section>
      </div>

      <section className="panel" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <span className="label">Versión de modelos activa</span>
          <p className="mono" style={{ margin: '4px 0 0', color: 'var(--color-acid)' }}>{data.despliegue_activo ?? 'Ninguna: el servicio de análisis no está disponible'}</p>
        </div>
        <Link className="text-link" to="/admin/modelos">Gestionar versiones <span aria-hidden="true">→</span></Link>
      </section>
    </div>
  );
}
