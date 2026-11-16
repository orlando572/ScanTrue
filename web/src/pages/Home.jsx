import { Link } from 'react-router-dom';
import { CriterionIcon, ResultCard } from '../components/Analysis.jsx';
import { CountUp } from '../components/ui.jsx';
import { publicApi } from '../lib/api.js';
import { useLoad } from '../lib/hooks.js';
import { CRITERIA, presentAnalysis, share } from '../lib/presentation.js';

const STEPS = [
  { title: 'Elige la noticia', text: 'Con la extensión de ScanTrue en tu navegador, selecciona el titular y algunos párrafos de la noticia que estás leyendo.' },
  { title: 'La revisamos', text: 'Dos sistemas de inteligencia artificial, entrenados con noticias reales y falsas, leen el texto por separado y dan su opinión.' },
  { title: 'Mira el resultado', text: 'El análisis se publica en esta página para que cualquiera pueda consultarlo. Nunca mostramos quién lo hizo.' },
];

const CRITERIA_TEXT = [
  { key: 'bilstm', state: 'Disponible', text: 'Lee la noticia de principio a fin, palabra por palabra, y busca formas de redactar típicas de las noticias falsas.' },
  { key: 'mbert', state: 'Disponible', text: 'Entiende cada palabra según las que la rodean, como lo haría un lector en español. Su opinión es la que más cuenta en el resultado final.' },
  { key: 'web', state: 'Próximamente', text: 'Buscará en otras fuentes si lo que dice la noticia está confirmado, desmentido o si todavía no hay información.' },
];

export default function Home({ health }) {
  const summary = useLoad((signal) => publicApi('/publico/resumen', { signal }), []);
  const latest = useLoad((signal) => publicApi('/publico/analisis?limit=3', { signal }), []);
  const data = summary.data;
  const total = data?.total ?? 0;
  const disagreements = data?.comparacion?.discrepan ?? 0;
  const pairs = (data?.comparacion?.coinciden ?? 0) + disagreements;

  return (
    <div className="shell home">
      <section className="hero boot">
        <h1>SCAN<span>//</span>TRUE</h1>
        <p className="hero-question">¿Dudas de una noticia?</p>
        <p className="hero-lead">
          Selecciona su texto con la extensión de ScanTrue y te decimos si podría ser una noticia falsa o real.
        </p>
        <div className="hero-actions">
          <Link className="btn" to="/resultados">Ver resultados</Link>
          <a className="btn btn--ghost" href="#como-funciona">Cómo funciona</a>
        </div>
        <div className="counters" aria-live="polite">
          <div className="counter"><span className="label">Análisis publicados</span><b><CountUp value={data ? total : null} /></b></div>
          <div className="counter"><span className="label">Últimos 7 días</span><b><CountUp value={data ? data.ultimos_7_dias : null} /></b></div>
          <div className="counter"><span className="label">Modelos que coinciden</span><b>{data && pairs > 0 ? <><CountUp value={share(data.comparacion.coinciden, pairs)} /> %</> : '—'}</b></div>
          <div className="counter"><span className="label">Páginas de origen</span><b><CountUp value={data ? data.dominios.length : null} /></b></div>
          {data?.verificaciones_web > 0 && (
            <div className="counter"><span className="label">Verificados con fuentes</span><b><CountUp value={data.verificaciones_web} /></b></div>
          )}
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
              <h3 className="h-panel">{step.title}</h3>
              <p className="muted" style={{ margin: 0 }}>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2 className="display h-page">Las tres revisiones</h2>
          <span className="label">Dos disponibles · una en camino</span>
        </div>
        <div className="grid-3 boot">
          {CRITERIA_TEXT.map((item) => (
            <article key={item.key} className="panel" style={{ '--edge': `color-mix(in srgb, ${CRITERIA[item.key].color} 45%, var(--color-line))` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <CriterionIcon name={item.key} />
                <span className={`tag ${item.state === 'Disponible' ? 'tag--ok' : 'tag--warn'}`}>{item.state}</span>
              </div>
              <h3 className="h-panel" style={{ color: CRITERIA[item.key].color }}>{CRITERIA[item.key].name}</h3>
              <p className="muted" style={{ margin: 0 }}>{item.text}</p>
            </article>
          ))}
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
