import { Link } from 'react-router-dom';
import { CriterionIcon, ResultCard } from '../components/Analysis.jsx';
import { ServiceStrip } from '../components/Shell.jsx';
import { CountUp } from '../components/ui.jsx';
import { publicApi } from '../lib/api.js';
import { LEVELS } from '../lib/filters.js';
import { useLoad } from '../lib/hooks.js';
import { CRITERIA, presentAnalysis, share } from '../lib/presentation.js';

const STEPS = [
  { title: 'Marca el texto', text: 'Con la extensión de ScanTrue seleccionas el titular y unos párrafos de la noticia en la página donde la estás leyendo.' },
  { title: 'Dos modelos lo leen', text: 'BiLSTM y BETO leen los fragmentos y cada uno estima si el texto se parece más a una noticia falsa o a una real.' },
  { title: 'El resultado queda aquí', text: 'Cada análisis se publica en esta página con sus fragmentos y las salidas de los modelos, sin identificar a quien lo hizo.' },
];

const CRITERIA_TEXT = [
  { key: 'bilstm', state: 'Activo', text: 'Red neuronal recurrente que recorre el texto palabra por palabra.' },
  { key: 'mbert', state: 'Activo', text: 'Modelo transformer en español que lee cada palabra en su contexto. Es el que más pesa en el resultado combinado.' },
  { key: 'web', state: 'Próximamente', text: 'Contrastará las afirmaciones del texto con fuentes externas y dirá si las respaldan, las contradicen o falta evidencia.' },
];

export default function Home({ health }) {
  const summary = useLoad((signal) => publicApi('/publico/resumen', { signal }), []);
  const latest = useLoad((signal) => publicApi('/publico/analisis?limit=3', { signal }), []);
  const data = summary.data;
  const total = data?.total ?? 0;
  const disagreements = data?.comparacion?.discrepan ?? 0;
  const pairs = (data?.comparacion?.coinciden ?? 0) + disagreements;

  return (
    <div className="shell">
      <section className="hero boot">
        <span className="label label--accent">Consola pública de análisis de noticias</span>
        <h1>SCAN<span>//</span>TRUE</h1>
        <p className="hero-lead">
          Dos modelos de lenguaje leen fragmentos de una noticia y muestran si se parece más a una
          noticia falsa o a una real.
        </p>
        <p className="hero-note">Es una orientación, no una verificación de los hechos.</p>
        <div className="hero-actions">
          <Link className="btn" to="/resultados">Ver resultados <span aria-hidden="true">→</span></Link>
          <a className="btn btn--ghost" href="#como-funciona">Cómo funciona</a>
        </div>
        <div className="counters" aria-live="polite">
          <div className="counter"><span className="label">Análisis publicados</span><b><CountUp value={data ? total : null} /></b></div>
          <div className="counter"><span className="label">Últimos 7 días</span><b><CountUp value={data ? data.ultimos_7_dias : null} /></b></div>
          <div className="counter"><span className="label">Modelos que coinciden</span><b>{data && pairs > 0 ? <><CountUp value={share(data.comparacion.coinciden, pairs)} /> %</> : '—'}</b></div>
          <div className="counter"><span className="label">Páginas de origen</span><b><CountUp value={data ? data.dominios.length : null} /></b></div>
        </div>
      </section>

      <section className="section" id="como-funciona">
        <div className="section-head">
          <h2 className="display h-page">Cómo funciona</h2>
          <span className="label">Tres pasos</span>
        </div>
        <div className="grid-3 boot">
          {STEPS.map((step, index) => (
            <article key={step.title} className="panel panel--mark">
              <span className="step-n" aria-hidden="true">0{index + 1}</span>
              <h3 className="h-panel" style={{ margin: '14px 0 8px' }}>{step.title}</h3>
              <p className="muted" style={{ margin: 0 }}>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="display h-page">Tres criterios</h2>
          <span className="label">Dos activos · uno en camino</span>
        </div>
        <div className="grid-3 boot">
          {CRITERIA_TEXT.map((item) => (
            <article key={item.key} className="panel" style={{ '--edge': `color-mix(in srgb, ${CRITERIA[item.key].color} 45%, var(--color-line))` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <CriterionIcon name={item.key} />
                <span className={`tag ${item.state === 'Activo' ? 'tag--ok' : 'tag--warn'}`}>{item.state}</span>
              </div>
              <h3 className="h-panel" style={{ margin: '16px 0 8px', color: CRITERIA[item.key].color }}>{CRITERIA[item.key].name}</h3>
              <p className="muted" style={{ margin: 0 }}>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="display h-page">Lo analizado hasta hoy</h2>
          <ServiceStrip health={health} />
        </div>
        <div className="panel">
          <span className="label">Reparto por nivel del resultado</span>
          {total > 0 ? (
            <>
              <div className="level-bar" style={{ marginTop: 12 }} role="img" aria-label={LEVELS.map((level, index) => `${level.label}: ${data.niveles[index]}`).join('; ')}>
                {LEVELS.map((level, index) => (data.niveles[index] > 0
                  ? <i key={level.value} className={`tone-${level.tone}`} style={{ flex: data.niveles[index] }} />
                  : null))}
              </div>
              <div className="legend">
                {LEVELS.map((level, index) => (
                  <span key={level.value} className={`tone-${level.tone}`}>
                    <i className="led" />{level.label} · {data.niveles[index]}
                  </span>
                ))}
              </div>
              {disagreements > 0 && (
                <p className="muted" style={{ margin: '16px 0 0' }}>
                  En {disagreements} análisis los dos modelos no coincidieron:
                  son los casos donde más conviene leer con cuidado.
                </p>
              )}
            </>
          ) : (
            <p className="muted" style={{ margin: '12px 0 0' }}>
              {summary.error ? 'No pudimos leer el resumen: la API no responde.' : summary.loading ? 'Leyendo el resumen…' : 'Todavía no hay análisis publicados.'}
            </p>
          )}
        </div>
      </section>

      {latest.data?.elementos?.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2 className="display h-page">Últimos resultados</h2>
            <Link className="text-link" to="/resultados">Ver todos <span aria-hidden="true">→</span></Link>
          </div>
          <div className="cards boot">
            {latest.data.elementos.map((item) => (
              <ResultCard key={item.id} view={presentAnalysis(item)} to={`/resultados/${item.id}`} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
