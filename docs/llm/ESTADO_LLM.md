# Estado del LLM (incremento 2): qué se hizo y qué falta

**Fecha del resumen:** 15 nov 2026. **Rama:** `feature/llm` (solo local: no está subida a GitHub). **Plan completo:** [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md).

Este documento es un resumen para ponerse al día. Cada fase tiene su documento de detalle, enlazado abajo.

## 1. Qué es

Después de que BiLSTM y BETO dan el resultado rápido, ScanTrue **contrasta el texto con fuentes de internet** y publica un tercer criterio: una **conclusión** (`respaldada`, `contradicha`, `fuera_de_contexto` o `evidencia_insuficiente`) con sus afirmaciones y sus fuentes con enlace. Corre aparte y en segundo plano: el resultado rápido no se retrasa y la verificación aparece en la web cuando termina.

**Cómo funciona hoy**

1. `POST /analisis` guarda el análisis y deja una fila `pendiente` en la cola.
2. Un trabajador dentro de la API la toma y un LLM local (Qwen3-4B-Instruct-2507, variante Q8_0 de 8 bits, servido con `llama-server` en la RTX 5060) extrae las afirmaciones comprobables del texto.
3. Cada afirmación se busca en internet (Tavily), se descargan las páginas con defensas de red, se eligen los pasajes relevantes y el LLM da un veredicto con **cita literal**. El backend comprueba que la cita exista en la página descargada y que cada enlace se haya descargado de verdad.
4. Una **regla fija** (no el LLM) saca la conclusión del caso; el LLM solo redacta el resumen.
5. La web pública y el panel de administración muestran estado, conclusión, resumen, afirmaciones y fuentes.

Si el LLM, internet o la cola fallan, el análisis rápido no se ve afectado: la verificación queda reintentando o `fallida` con su causa (3 intentos, esperas de 1, 5 y 15 minutos).

## 2. Fases

| Fase | Qué es | Estado | Commit | Detalle |
| --- | --- | --- | --- | --- |
| 0 | Entorno y Supabase de desarrollo propio (D12) | **Hecha** | `42b08a1` | [Plan](PLAN_INCREMENTO_2.md) |
| 1 | Servidor LLM y cliente (`llm_client.py`) | **Hecha**; falta probar la conexión entre dos equipos (D8) | `42b08a1` | [MEDICIONES_LLM.md](MEDICIONES_LLM.md) |
| 2 | Migración 009, cola y trabajador | **Hecha** | `21c03d1` | [Plan](PLAN_INCREMENTO_2.md) |
| 3 | Extracción de afirmaciones y base de verificaciones anteriores (migración 010) | **Hecha** | `9d73d91` | [BASE_AFIRMACIONES.md](BASE_AFIRMACIONES.md) |
| 4 | Búsqueda web, descarga y juicio por afirmación | **Hecha** (medida con Tavily; Brave sin medir) | `fb1301e` | [BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md) |
| 5 | Conclusión, resumen y trabajador completo | **Hecha**, con un límite de calidad (sección 4) | `5425b2b` | [CONCLUSION_Y_TRABAJADOR.md](CONCLUSION_Y_TRABAJADOR.md) |
| 6 | Web y panel (cola, pausa, reintento, filtros) | **Hecha** | `15fb038` | [WEB_Y_PANEL.md](WEB_Y_PANEL.md) |
| 7 | **Evaluación y ajuste** | **En curso** (sección 3), sin commit | — | [EVALUACION_VERIFICACION.md](EVALUACION_VERIFICACION.md) |
| 8 | Cierre y documentación | **Pendiente** | — | [Plan](PLAN_INCREMENTO_2.md) |

Pruebas: **388 en el backend** (con la Fase 7 y la fuente previa) y 16 en la web, todas pasan. Las pruebas del backend no necesitan LLM ni internet.

## 3. Fase 7 (la que está en curso)

Es la que dice si el sistema sirve. Se mide con un conjunto propio, `verificacion_v1`: **80 casos** (20 por conclusión; 40 para ajustar y 40 de **prueba final**, que se abre una sola vez), comparado con dos referencias: A, «siempre evidencia insuficiente», y B, el mismo LLM sin búsqueda.

**Hecho**
- El **arnés de evaluación** completo en `backend/evaluacion/` (47 pruebas): formato y validación de los casos, tabla de equivalencias escrita antes de etiquetar, evidencia en vivo y congelada, referencias A y B, métricas con intervalos de incertidumbre, comprobación de citas y enlaces, informe por corrida y las salvaguardas de la prueba final.
- Un **piloto** de 6 casos reales que corrió de punta a punta: unos 50 s y 9 búsquedas por caso, 18 fuentes presentadas y las 18 comprobadas aparte, **0 direcciones inventadas**. Acertó 1 de 6, lo que no significa nada con 6 casos: solo prueba que el arnés mide.
- **Tanda 1 del conjunto armada:** 20 casos `contradicha` (10 de ajuste y 10 de prueba final) de Newtral, Chequeado, Ecuador Chequea, La República, Maldita.es y La Silla Vacía, con hechos de 2026. Están **en revisión por una persona** (se está revisando la hoja ahora).

**Falta**
1. Terminar la revisión de la tanda 1 y armar las otras tres tandas de 20: `fuera_de_contexto`, `evidencia_insuficiente` y `respaldada`.
2. Congelar el conjunto (huella SHA-256) y correr las referencias A y B y el sistema sobre el conjunto de ajuste.
3. Ajustar **solo con el conjunto de ajuste**: instrucciones, tope de afirmaciones y la regla de conclusión (hay 5 ajustes candidatos en [CONCLUSION_Y_TRABAJADOR.md](CONCLUSION_Y_TRABAJADOR.md)).
4. Fijar la cifra mínima de F1 macro, abrir la prueba final **una sola vez** y escribir el informe de resultados.

**Para aceptar el incremento** (prueba final): 0 URL inventadas, citas válidas ≥ 95 % y F1 macro por encima de las dos referencias y de la cifra mínima fijada.

## 4. Límites de calidad conocidos

- **La conclusión del caso hoy se equivoca con facilidad.** En el recorrido real de la Fase 5, de 3 casos normales acertó 1: basta una afirmación mal juzgada para decidir el caso. La regla se ajustará en la Fase 7; **por eso `VERIFICATION_ENABLED` está apagado por defecto y no debe encenderse donde el público vea resultados** hasta entonces.
- `respaldada` casi no se alcanza con la regla actual (exige todas las afirmaciones `apoyada`) y `fuera_de_contexto` es poco fiable con este modelo; el piloto lo confirmó.
- El filtro contra órdenes escondidas en textos o páginas es una **defensa parcial** (detecta 7 de 16 órdenes nuevas en la prueba).
- Casi 1 de cada 5 páginas descargadas se descarta (sobre todo PDF), y las redes sociales y el video no entregan texto.
- En el piloto, un caso con 5 afirmaciones y 2 consultas cada una costó unos 50 s y unas 9 búsquedas; **desde el cambio de la sección 6 el tope es de 3 afirmaciones y 1 consulta**, es decir, hasta 3 búsquedas por noticia (sin medir todavía). El LLM no es idéntico de una corrida a otra, lo que hay que tener en cuenta al repetir mediciones.
- La pausa del trabajador vive en memoria: no se conserva al reiniciar la API.

## 5. Lo que necesita al equipo

- **Búsqueda (D3):** se midió Tavily; Brave no, por falta de clave. Los términos de Brave **prohíben guardar los resultados y usarlos para evaluar modelos de IA**, lo que parece chocar con guardar las fuentes y con la Fase 7. Hace falta decidir cuál se usa.
- **Presupuesto de búsqueda:** una corrida en vivo de 40 casos gasta unos 360 créditos de Tavily (el cupo gratis es de 1.000 al mes). Sin decisión, la Fase 7 se itera solo con corridas congeladas.
- **Supabase de producción:** nuestras migraciones 009 y 010 (la 008 es la de Orlando, estándar de datasets) solo se aplicaron en el proyecto de desarrollo; se renumeraron el 16 nov 2026 porque antes se llamaban 008 y 009 y chocaban con la 008 de `develop`. Antes de aplicarlas en el de producción hay que coordinarlo con quien lo administra.
- **Conexión entre equipos (D8):** el LLM está pensado para correr en un equipo aparte (`LLM_BASE_URL` y clave); solo se probó en `127.0.0.1`.
- **Confirmar D3 a D7:** estaban asignadas a Orlando en el borrador y se registraron como decididas el 15 nov; conviene que él las confirme.
- **Documentación pendiente:** `docs/INCREMENTOS.md` decía «cuantizado a 4 bits» y se corrigió a 8 bits (Q8_0, la variante elegida) el 15 nov 2026. La Fase 8 también actualizará `backend/README.md`, `web/README.md` (hoy dice que la verificación no existe), y los documentos de base de datos, diccionario de datos y diagrama de clases.

## 6. Cambio posterior: límites y fuente previa

Después de las fases anteriores se hicieron estos cambios (detalle en [FUENTE_PREVIA.md](FUENTE_PREVIA.md); sin commit). La API de Google se probó con 3 afirmaciones y el recorrido completo con 5 afirmaciones y un caso (resultados abajo):

- **3 afirmaciones por noticia** (antes 5) y **1 consulta por afirmación** (antes 2); páginas por afirmación siguen en 4. El prompt de extracción pasó a `extraccion-v2` y pide «las 3 más importantes»: es un **cambio de comportamiento que se mide en la Fase 7**.
- **Fuente previa:** antes de buscar en Tavily se consulta Google Fact Check Tools (verificaciones ya publicadas). Si con eso el juez puede dar un veredicto, no se busca en la web; si dice «insuficiente», se busca también en Tavily y se juzga con toda la evidencia. Se activa con `FACTCHECK_API_KEY`; sin ella todo sigue como antes. **A esa fuente va una consulta corta (2 o 3 palabras clave) escrita por el LLM**, que añade unos 0,6 s por afirmación (unos 1,8 s por noticia de 3 afirmaciones). Con la corta, 6 de 10 afirmaciones con verificación publicada obtuvieron un resultado pertinente, igual que con la consulta larga (pero con más resultados pertinentes cada una), y 4 siguen sin resultados con cualquier consulta. Se probó una segunda consulta aún más corta si la primera daba 0 y se quitó: no ayudaba y añadía ruido.
- Pruebas del backend: 388 (25 nuevas). Se arregló la prueba intermitente de la Fase 6 (solo la prueba, no el código).
- **Recorrido real con LLM, Google y Tavily (5 afirmaciones y un caso de 3):** la fuente previa bastó en 7 de 13 verificaciones y ahorró 3 de 5 créditos de Tavily, pero no ahorró tiempo (+0,6 s por afirmación en esa mezcla) y en una afirmación dio un veredicto equivocado con evidencia de otra afirmación (`fuera_de_contexto`). El juez dijo «insuficiente» y se pasó a Tavily en 1 de 13. Por eso se decidió que **solo «apoyada» o «contradicha» detengan la búsqueda; con «fuera_de_contexto» o «insuficiente» se busca también en Tavily** (implementado). Con eso, Milei pasaba a Tavily pero seguía en `fuera_de_contexto` porque el juicio final mezclaba las páginas de las dos fuentes; por eso, **si la fuente previa no basta, el juicio final usa solo las páginas de la web**, y Milei sale `contradicha` (comprobado con datos reales; 3 ejecuciones de Milei: 10,7 s de media frente a 6,6 s solo con la web, de los cuales unos 3,0 s son atribuibles a la fuente previa). Con la fuente previa que no encuentra nada, el coste es de unos 1,1 a 1,2 s por afirmación; si encuentra algo que no basta, de unos 3,0 s, sin ahorrar créditos (10 créditos gastados en esa medición, 5 por camino). Detalle: secciones 9, 9.1, 9.2 y 9.3 de FUENTE_PREVIA.md.

## 7. Estado de Git y cómo probarlo

- `feature/llm` tiene 6 commits locales (de `42b08a1` a `15fb038`) sobre `develop` en `7f913b5`. **Nada de esta rama está en GitHub.** El trabajo de la Fase 7 (arnés, piloto y tanda 1) y el cambio de la sección 6 todavía no tienen commit. Los casos y la evidencia están en `datasets/verificacion_v1/`, fuera de Git.
- Para arrancar la API con la verificación se necesita `llama-server` levantado y las claves del proyecto de desarrollo (Supabase de desarrollo, LLM y Tavily) en `backend/.env.desarrollo`; `backend/.env` no se toca. Los pasos y los comandos están en [MEDICIONES_LLM.md](MEDICIONES_LLM.md) y [EVALUACION_VERIFICACION.md](EVALUACION_VERIFICACION.md).
- Pruebas del backend (388, 14 s, desde Git Bash): `PYTHONPATH=. backend/.venv/Scripts/python.exe -m unittest $(ls backend/tests/test_*.py | sed 's#/#.#g; s#\.py$##')`. También se puede correr un solo módulo, por ejemplo `-m unittest backend.tests.test_evaluacion`.
