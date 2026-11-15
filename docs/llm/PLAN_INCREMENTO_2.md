# Plan del incremento 2: verificación diferida con LLM y búsqueda web

**Estado:** borrador revisado; decisiones D1–D16 tomadas el 15 nov 2026 (sección 4.8). Rama `feature/llm`, partiendo de `develop` en `7f913b5` (12 nov 2026).
**Descripción del incremento:** [INCREMENTOS.md](../INCREMENTOS.md), sección 2.
**Qué es este documento:** un plan de trabajo desde los requisitos hasta el incremento funcionando. Lo que ya existe en el repositorio se marca como tal; las decisiones del equipo están en la sección 4.8, con lo que queda por cerrar de cada una.

## 1. Objetivo

Después de que BiLSTM y BETO den el resultado rápido, ScanTrue contrasta el texto con fuentes externas y publica un **tercer criterio**: una conclusión (`respaldada`, `contradicha`, `fuera_de_contexto` o `evidencia_insuficiente`) con sus afirmaciones y sus fuentes. El resultado rápido no se retrasa: la verificación corre aparte, en segundo plano, y aparece en la web cuando termina.

**Incremento terminado cuando:** un análisis creado desde la extensión pasa solo de `pendiente` a `completada`, y la web pública y el panel muestran la conclusión, las afirmaciones y las fuentes con enlace, sin intervención manual y sin detener la API.

## 2. Punto de partida (revisado en `develop`)

### 2.1. Lo que ya existe y se reutiliza

| Pieza | Dónde | Qué aporta al incremento 2 |
| --- | --- | --- |
| Tabla `verificaciones_web` | [007_revision_datasets.sql](../../backend/db/migrations/007_revision_datasets.sql) | `analisis_id`, `estado` (`pendiente`, `en_proceso`, `completada`, `fallida`), `conclusion`, `resumen` (≤ 4000), `afirmaciones` y `fuentes` (jsonb, listas), `modelo_llm`. Hoy está **vacía**. Una restricción obliga a que `conclusion` exista si y solo si el estado es `completada`. |
| Esquema `WebVerification` | `backend/schemas/public.py` | La API pública ya devuelve `verificacion_web` en lista y detalle (hoy `null`). |
| Filtro `verificacion` | `backend/api/public_routes.py`, `web/src/components/Filters.jsx` | Ya acepta `sin_verificar` y las cuatro conclusiones. |
| Presentación del tercer criterio | `web/src/lib/presentation.js` (`presentVerification`), `web/src/components/Analysis.jsx` (`CriteriaList`) | Ya pinta estado, conclusión, resumen, afirmaciones y fuentes. Lee `titulo`/`texto`/`afirmacion` y `url` de cada elemento. Hoy muestra «Aún no disponible». |
| Contador | función SQL `resumen_plataforma` (`verificaciones_web`) | Ya cuenta las completadas para portada y panel. |
| Patrón de cola durable | `reclamar_registro_blockchain()` ([003](../../backend/db/migrations/003_blockchain_registry.sql)) y `backend/blockchain/worker.py` | Reserva con `for update skip locked`, reintentos con espera, vencimiento de la reserva y bucle asíncrono lanzado en `lifespan` de `backend/app.py`. La cola de verificación sigue el mismo diseño. |
| Texto a verificar | `analisis.texto_original` (≤ 20.000 caracteres), `fragmentos`, `url`, `dominio` | El LLM recibe el fragmento original completo, no el prefijo recortado de cada modelo. |
| Búsqueda de parecidos en SQL | extensión `pg_trgm` (migración 007) | Sirve para la consulta a «verificaciones anteriores» sin añadir infraestructura. |
| Revisión y datasets | `revisiones`, `dataset_items.evidencia` | La evidencia de una verificación puede alimentar la revisión del incremento 3. |

### 2.2. Lo que falta (el trabajo del incremento)

1. No existe el **servidor del LLM** ni un cliente para llamarlo.
2. No existe **ninguna búsqueda web** ni descarga de páginas.
3. `POST /analisis` **no crea** la fila de verificación: nada entra en cola.
4. La tabla no tiene intentos, próxima ejecución, error ni versión de prompts; no hay función para reclamar trabajo.
5. No hay **base de afirmaciones ya verificadas** (el paso 3 del incremento: «primero la base de verificaciones anteriores»).
6. No hay prompts, ni validación de lo que responde el LLM, ni regla para pasar de afirmaciones a conclusión.
7. No hay controles del administrador (ver la cola, reintentar, pausar).
8. No hay **conjunto de evaluación** ni métricas de la verificación.
9. Este equipo ya tiene `backend/.venv` (Python 3.14.7, FastAPI, Supabase, web3, httpx y PyTorch 2.13.0 con CUDA 13). No existen `bilstm/.venv` ni `backend/.deps`, que son los que usa el README, así que se trabaja con `backend/.venv`. Falta añadir lo propio del incremento: extractor de texto web y las dependencias de la búsqueda elegida.

### 2.3. Equipo disponible

- Este equipo: **NVIDIA GeForce RTX 5060 Laptop, 8 GB de VRAM** (medido con `nvidia-smi`). Es la GPU asignada al LLM en [INCREMENTOS.md](../INCREMENTOS.md).
- Backend y base de datos: la RTX 3050 de Orlando (según INCREMENTOS.md). El LLM se llama por red desde el backend, así que la dirección del servidor LLM es configuración, no código.
- Python 3.14.7 en este equipo. Las librerías de inferencia de LLM suelen tardar en publicar versiones para Python nuevos: por eso el plan usa un **servidor externo al proceso de Python** (sección 4.2) y no una librería de inferencia dentro del backend. **A comprobar en la Fase 0.**

## 3. Alcance

**Entra:** cola de verificación, extracción de afirmaciones, consulta a verificaciones anteriores, búsqueda web, juicio sobre la evidencia, conclusión con fuentes, publicación en la web existente, controles mínimos del administrador, evaluación propia de la verificación y documentación.

**No entra** (pertenece a otros incrementos o no se pidió):
- Reentrenar o ajustar Qwen (QLoRA): es el incremento 4B.
- Cambiar BiLSTM, BETO, la calibración o el resultado unificado. La verificación es un criterio **adicional** y no modifica `probabilidad_falsa`.
- Cambiar la extensión de Chrome. Sigue enviando análisis como hoy; la verificación se ve en la web.
- Rediseñar la web: solo se completan los puntos donde ya espera la verificación.
- Registrar la verificación en blockchain.
- Verificar los análisis creados **antes** de aplicar la migración 008 (D9): quedan sin verificación y la web los muestra como `sin_verificar`.

## 4. Requisitos y diseño

### 4.1. Flujo completo

```
Extensión ─ POST /analisis ─► BiLSTM + BETO ─► guarda análisis ─► responde al usuario (rápido)
                                   │
                                   └─► crea verificaciones_web (estado = pendiente)
                                                │
                       Trabajador de verificación (segundo plano, 1 caso a la vez)
                                                │
   1. Reclamar caso ─► 2. LLM extrae afirmaciones verificables
                                                │
                  por cada afirmación:  3. ¿Está en la base de verificaciones anteriores?
                                              sí ─► reutilizar (con su fecha y fuentes)
                                              no ─► 4. Consultas de búsqueda ─► 5. Buscar en internet
                                                    ─► 6. Descargar y extraer pasajes
                                                    ─► 7. LLM juzga cada afirmación con esos pasajes
                                                │
                  8. Regla de conclusión + resumen ─► 9. Guardar (completada) ─► la web lo muestra
```

**D6:** se verifican **todos** los análisis. Como el LLM atiende un caso a la vez, el orden de la cola es: primero los casos donde BiLSTM y BETO discrepan, luego los de nivel alto (4 y 5) y después el resto por antigüedad.

La verificación **no bloquea ni cambia** la respuesta de `POST /analisis`. Si falla el LLM o la búsqueda, el análisis rápido sigue intacto y el caso queda `fallida` o vuelve a la cola.

### 4.2. Servidor del LLM (RTX 5060)

| Requisito | Detalle |
| --- | --- |
| Modelo | Qwen de 4B parámetros. INCREMENTOS.md habla de cuantización a 4 bits; la variante elegida es de 8 bits (Q8_0). **D1:** en la Fase 1 se compararon dos cuantizaciones de Qwen3-4B-Instruct-2507 (Q4_K_M y Q8_0) con los mismos textos y se eligió **Q8_0** ([MEDICIONES_LLM.md](MEDICIONES_LLM.md)). |
| Cabida | Los pesos ocupan 2,5 GB en 4 bits (Q4_K_M) y 4,3 GB en 8 bits (Q8_0); la caché de contexto crece con la longitud. Medido en la Fase 1 con Q8_0: 5,9 GB de VRAM con contexto 8192 y contexto estable hasta 16.384; se usa `-c 8192` ([MEDICIONES_LLM.md](MEDICIONES_LLM.md)). |
| Interfaz | **D2:** `llama-server` de llama.cpp con modelo GGUF, lanzado como proceso aparte, con API compatible con OpenAI (`/v1/chat/completions`). Ollama queda descartado. |
| Red | **D8:** el servidor corre en el equipo de la 5060 y el backend lo llama por `LLM_BASE_URL`. Hay que escuchar en la red local (no solo en `127.0.0.1`), exigir clave de API (`--api-key`) y abrir solo ese puerto entre los dos equipos. En desarrollo ambos pueden estar en el mismo equipo con la misma configuración. |
| Salida estructurada | Es **obligatorio** poder forzar JSON con esquema (gramática o `response_format`). Sin eso, un modelo de 4B rompe el formato con frecuencia. |
| Uso de herramientas | INCREMENTOS.md pide *tool use*. En este plan la búsqueda la ejecuta el **backend** y el LLM solo decide qué consultar y juzga lo recuperado (ver 4.5). Así el modelo no tiene acceso directo a internet. |
| Concurrencia | 1 solicitud a la vez por GPU. El trabajador procesa un caso por vez. |
| Pausa | La GPU debe poder liberarse (incremento 4B). Por eso existe el interruptor de pausa de la sección 4.7. |

### 4.3. Datos: migración `008_verificacion_web.sql` (y su reversión)

Sigue el estilo de 006/007: función `security invoker`, `search_path` vacío, RLS sin políticas, permisos solo para `service_role`, y archivo de reversión en `backend/db/rollback/`.

**Estados (aclaración):** `pendiente` es «en cola»; también es adonde vuelve un caso tras una falla pasajera, con su `proximo_intento`. `en_proceso` es un caso reservado por el trabajador; si la reserva vence, otro intento lo retoma. `fallida` es **final**: se llega a ella al agotar los intentos (D11) y solo el administrador la devuelve a `pendiente`. `completada` es final.

**Cambios en `verificaciones_web`:**

| Columna nueva | Para qué |
| --- | --- |
| `intentos integer not null default 0` | Contar reintentos. |
| `proximo_intento timestamptz not null default now()` | Espera entre reintentos y vencimiento de la reserva. |
| `ultimo_error text` | Causa de la última falla (`llm_no_disponible`, `busqueda_fallida`, `salida_invalida`, `tiempo_agotado`). |
| `copiada_de uuid` | Si el caso reutilizó la verificación de otro análisis con el mismo texto (D10), cuál fue. **Sin clave foránea a propósito:** una segunda relación entre `analisis` y `verificaciones_web` hace ambigua la incrustación de PostgREST (PGRST201) y rompe la web pública y el panel. |
| `version_prompts text` | Con qué versión de instrucciones se generó (para comparar en la evaluación). |
| `iniciado_en`, `terminado_en timestamptz` | Medir duración por caso. |
| Índice parcial por `(proximo_intento, analisis_id)` donde `estado in ('pendiente','en_proceso')` | Cola eficiente. |

**Funciones:**
- `encolar_verificacion(p_analisis_id uuid)`: inserta `pendiente` y no hace nada si ya existe.
- `reclamar_verificacion_web()`: devuelve un `analisis_id`, lo pasa a `en_proceso`, suma un intento y fija el vencimiento de la reserva. Mismo patrón que `reclamar_registro_blockchain()`. Ordena según D6: primero `analisis.discrepa`, luego `probabilidad_unificada` alta (niveles 4 y 5) y después `fecha` ascendente. No reclama un caso con `intentos` igual al máximo (D11): lo marca `fallida`.
- `copiar_verificacion_web(p_analisis_id uuid)`: si existe otro análisis con el mismo `hash_texto` y una verificación `completada` aún vigente (30 días; 7 si su conclusión es `evidencia_insuficiente`, D5), copia estado, conclusión, resumen, afirmaciones, fuentes y `modelo_llm`, y anota `copiada_de` (D10). Devuelve si copió.
- `completar_verificacion_web(...)`: guarda conclusión, resumen, afirmaciones, fuentes y `modelo_llm` en una sola operación (respeta la restricción de la tabla).

**Tabla nueva `afirmaciones_verificadas` (base de verificaciones anteriores):**

| Columna | Contenido |
| --- | --- |
| `id`, `texto`, `texto_normalizado`, `hash_texto` | La afirmación, normalizada para comparar (minúsculas, sin puntuación), y su hash. |
| `veredicto` | `apoyada`, `contradicha`, `fuera_de_contexto`, `insuficiente`. |
| `fuentes jsonb` | Las fuentes con las que se decidió. |
| `modelo_llm`, `version_prompts`, `verificado_en`, `expira_en` | Para saber cuándo desconfiar de un resultado viejo. |
| `analisis_origen uuid` (`on delete set null`) | Procedencia; borrar el análisis no borra la base. |

Índices: único por `hash_texto` y `gin` con `gin_trgm_ops` sobre `texto_normalizado` (la extensión ya está instalada).

**Estructura de los jsonb** (compatible con `presentVerification`, que ya lee `texto`, `titulo` y `url`):

```json
// afirmaciones
[{"id": 1, "texto": "…", "veredicto": "contradicha", "fuente_ids": [1, 3], "origen": "busqueda | base_anterior"}]
// fuentes
[{"id": 1, "titulo": "…", "url": "https://…", "dominio": "…", "extracto": "cita literal", "consultada_en": "2026-…"}]
```

### 4.4. Servicios del backend

Archivos nuevos, con la misma organización de `backend/services/` y `backend/repositories/`:

| Archivo | Responsabilidad |
| --- | --- |
| `services/llm_client.py` | Cliente del servidor LLM: envío, tiempo máximo, reintento, validación del JSON contra el esquema. Distingue «LLM caído» de «respuesta inválida». |
| `services/verification/prompts.py` | Instrucciones versionadas (`version_prompts`). Se guardan junto al resultado. |
| `services/verification/claims.py` | Paso de extracción de afirmaciones. |
| `services/verification/search.py` | Interfaz `SearchProvider` y un proveedor concreto (4.5). |
| `services/verification/fetch.py` | Descarga y extracción del texto de una página, con las defensas de 4.6. |
| `services/verification/passages.py`, `pipeline.py` | Selección de pasajes y el recorrido de una afirmación (`verify_claim`: consultas → búsqueda → descarga → pasajes → juicio). Añadidos en la Fase 4. |
| `services/verification/judge.py` | Juicio por afirmación y regla de conclusión. |
| `services/verification/conclusion.py`, `case.py` | Regla de conclusión y resumen (Paso 5) y el recorrido de un caso completo. Añadidos en la Fase 5. |
| `services/verification/untrusted.py`, `text.py` | Filtro de frases que parecen órdenes al modelo (4.6) y utilidades de texto. Añadidos en la Fase 4. |
| `services/verification/worker.py` | Bucle del trabajador: reclamar, procesar, guardar, reintentar. Se lanza en `lifespan` de `backend/app.py` como el de blockchain. |
| Cambios en `repositories/supabase.py` | Encolar, reclamar, completar, marcar fallida, consultar y guardar en `afirmaciones_verificadas`. |
| Cambios en `core/config.py` y `.env.example` | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT`, `SEARCH_PROVIDER`, `SEARCH_API_KEY`, `SEARCH_TIMEOUT`, `VERIFICATION_ENABLED`, `VERIFICATION_MAX_ATTEMPTS` (3, D11), `VERIFICATION_DESDE` (fecha de corte: el barrido solo encola análisis posteriores, D9) y los límites de la sección 4.6. |
| Cambio en `api/routes.py` (`analyze`) | Tras guardar el análisis, encolar. **Si encolar falla, el análisis no falla**: un barrido periódico del trabajador encola los análisis que no tengan fila. |

### 4.5. Pasos de la verificación

**Paso 0 — Texto ya verificado.** Antes de usar el LLM, el trabajador llama a `copiar_verificacion_web`. Si el mismo texto ya tiene una verificación vigente, la copia y termina el caso sin gastar GPU ni búsquedas (D10).

**Paso 1 — Extraer afirmaciones.** El LLM recibe el texto original y devuelve, con esquema forzado, hasta N afirmaciones **verificables** (hechos, cifras, atribuciones, fechas, lugares). Cada una debe poder entenderse sola (se reescribe sin pronombres ni referencias al texto). Las opiniones y los juicios de valor se descartan. Tope de afirmaciones por caso: propuesto 5 (a ajustar en la Fase 5). Si no hay ninguna verificable, el caso termina como `evidencia_insuficiente` con un resumen que lo explica.

**Paso 2 — Base de verificaciones anteriores.** Para cada afirmación: búsqueda **exacta** por hash del texto normalizado (minúsculas, sin tildes ni puntuación). Solo se reutiliza si no ha expirado, y se marca `origen: base_anterior` y se muestra como tal. **D5:** una afirmación ya verificada se reutiliza durante **30 días**, y solo **7 días** si su veredicto fue `insuficiente` (puede aparecer información nueva). El plan preveía además una búsqueda por similitud (`pg_trgm`) con un umbral; **la Fase 3 la midió y ningún umbral separa una paráfrasis de un cambio de un solo dato** (por ejemplo «Florida» por «Texas»), así que el usuario decidió reutilizar solo la coincidencia exacta. Ver [BASE_AFIRMACIONES.md](BASE_AFIRMACIONES.md).

**Paso 3 — Búsqueda web (hecha por el backend).** El LLM propone 1–2 consultas por afirmación; el backend las ejecuta con un `SearchProvider` y se queda con los mejores resultados. Se descargan solo las páginas elegidas, se extrae el texto y se seleccionan los pasajes más cercanos a la afirmación.

| Proveedor candidato | Ventaja | Riesgo |
| --- | --- | --- |
| SearXNG propio | Sin costo ni clave; control total | Hay que instalarlo y mantenerlo; los buscadores que agrega pueden bloquearlo |
| API comercial de búsqueda (Brave, Tavily, Serper u otra) | Estable y simple | Clave, límites de uso y posible costo |
| Raspado directo de un buscador | Nada que instalar | Frágil y contra los términos de uso; **no recomendado** |

**D3:** se usa una **API comercial** de búsqueda; SearXNG y el raspado quedan descartados. Cuál (Brave, Tavily, Serper u otra) se decide en la Fase 4, probando dos con el mismo conjunto de afirmaciones. El código depende solo de `SearchProvider`, así que cambiarla después no rehace nada. Las condiciones, límites y costos se comprueban al contratar, no se dan por conocidos aquí. **Fase 4:** el usuario eligió probar **Brave y Tavily**; ambas están implementadas detrás de `SearchProvider`. Las condiciones leídas en sus páginas oficiales y un hallazgo sobre los términos de Brave (prohíben guardar resultados y usarlos para evaluar IA) están en [BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md), sección 2.

**Paso 4 — Juicio por afirmación.** El LLM recibe la afirmación y los pasajes numerados y devuelve, con esquema: `veredicto` (`apoyada`, `contradicha`, `fuera_de_contexto`, `insuficiente`), los números de pasaje que usa y una cita literal. El backend **comprueba** antes de aceptar: (a) los pasajes citados existen, (b) la cita aparece textualmente en el pasaje, (c) la URL es una de las recuperadas. Si falla, el veredicto pasa a `insuficiente`. El modelo nunca inventa un enlace: solo se muestran URL que el backend descargó. **Añadido tras medir (Fase 4):** (d) una afirmación solo queda `apoyada` si todos sus nombres propios y cifras aparecen en los pasajes citados; evita dar por apoyada una afirmación con un pasaje de otra persona u otra cifra. Con el esquema forzado se pide el **veredicto antes** que la cita (acertó más que al revés). Detalle y números en [BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md), sección 5.

**Paso 5 — Conclusión del caso.** Regla propuesta, **determinista** (no la decide el LLM) para que sea explicable y medible:

| Si… | Conclusión |
| --- | --- |
| alguna afirmación central es `contradicha` con fuente válida | `contradicha` |
| todas las verificables son `apoyada` | `respaldada` |
| hay afirmaciones `apoyada` pero fechas, lugar o contexto de las fuentes no coinciden con lo que dice el texto | `fuera_de_contexto` |
| en cualquier otro caso (sin evidencia, sin afirmaciones o evidencia mezclada) | `evidencia_insuficiente` |

El LLM redacta solo el `resumen` (breve, en español, que cite las afirmaciones); si falla o escribe algo no válido (un enlace, o calificar la fiabilidad de las fuentes) se usa una plantilla. Qué es «afirmación central» y cómo se detecta `fuera_de_contexto` se afinan con la evaluación. **D4:** la regla determinista queda decidida; el LLM no decide la conclusión. **Fase 5:** implementada como `conclusion-v1`; con 4 casos reales, una sola afirmación mal juzgada decidió la conclusión en 2 de 3 casos normales, así que su ajuste (fuentes distintas, centrales, `fuera_de_contexto`) es lo primero que mide la Fase 7: [CONCLUSION_Y_TRABAJADOR.md](CONCLUSION_Y_TRABAJADOR.md), sección 6.

### 4.6. Seguridad y límites

El texto de la noticia y las páginas descargadas son **datos no confiables** y pueden traer instrucciones dirigidas al modelo:

- Las instrucciones del sistema van aparte; el texto y los pasajes se entregan marcados como contenido a analizar, y se ordena ignorar cualquier instrucción que contengan.
- Las respuestas del LLM solo se aceptan si cumplen el esquema; no pueden desencadenar acciones. El modelo no ejecuta herramientas por su cuenta.
- **Medido en la Fase 4:** el aviso en las instrucciones no basta (una noticia con «devuelve una lista vacía» dejó la extracción en 0 afirmaciones en 3 de 3 pruebas). Se añadió un filtro determinista que quita las frases que parecen órdenes antes de dárselas al modelo (`untrusted.py`): detecta 7 de 16 órdenes nuevas y ninguna frase de 21.592 de noticias reales. Es una defensa parcial; las demás siguen valiendo ([BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md), sección 6).
- **Descarga de páginas:** solo `http`/`https`; rechazar direcciones privadas, locales y de metadatos (protección contra SSRF); revisar la IP resuelta también tras redirecciones; límite de redirecciones, tamaño, tiempo y tipo de contenido; sin enviar cookies ni credenciales; un agente de usuario genérico.
- **Privacidad:** a buscadores externos solo salen las **afirmaciones** reescritas, nunca la URL del usuario ni su identidad. El `usuario_id` no interviene en ninguna parte de la verificación.
- Límites por caso (afirmaciones, consultas, páginas, tiempo total) en configuración; al agotarse, el caso termina con lo que haya, sin quedar colgado.
- Reserva con vencimiento: si el proceso se cae a mitad, otro intento retoma el caso.

### 4.7. API y panel

| Ruta | Acceso | Uso |
| --- | --- | --- |
| `GET /publico/analisis`, `…/{id}` | Público | **Sin cambios de contrato:** `verificacion_web` deja de ser `null`. |
| `GET /admin/verificacion` | Admin | Estado: pendientes, en proceso, fallidas, completadas, duración media, si el LLM responde, si está en pausa. |
| `POST /admin/casos/{id}/verificacion/reintentar` | Admin | Vuelve el caso a `pendiente`. |
| `POST /admin/verificacion/pausar` y `/reanudar` | Admin | Detiene el trabajador sin perder la cola (necesario para liberar la GPU en el incremento 4B). |

Panel: en el detalle del caso se muestra la verificación con el componente existente y un botón de reintento; el tablero de la portada del panel suma el estado de la cola. La web pública ya filtra y muestra; se comprueba y se retoca solo lo que falle con datos reales.

**Salud:** `GET /salud` añade `llm` (disponible o no) sin cambiar el estado `ok`/`degradado` actual de los modelos de clasificación: un LLM caído no degrada el análisis rápido.

### 4.8. Decisiones (revisión del 15 nov 2026)

| # | Decisión | Resultado | Queda por cerrar |
| --- | --- | --- | --- |
| D1 | Variante de Qwen 4B | **Qwen3-4B-Instruct-2507 Q8_0 (8 bits)**, elegida en la Fase 1 frente a Q4_K_M ([MEDICIONES_LLM.md](MEDICIONES_LLM.md)) | Actualizar [INCREMENTOS.md](../INCREMENTOS.md), que aún dice «4 bits» (se hará más adelante, por indicación del usuario) |
| D2 | Servidor del LLM | **`llama-server`** (llama.cpp), modelo GGUF; Ollama descartado | Comprobar la compilación o el binario con la 5060 en la Fase 0 |
| D3 | Búsqueda web | **API comercial** detrás de `SearchProvider`; SearXNG y raspado descartados. Se prueban **Brave y Tavily** (elección del usuario, Fase 4) | Cuál API: falta la comparación con las claves; antes, confirmar con Orlando si los términos de Brave (no guardar resultados, no usarlos para evaluar IA) permiten el uso que hacemos |
| D4 | Conclusión del caso | **Regla determinista** de 4.5; el LLM solo redacta el resumen | Definir «afirmación central» y `fuera_de_contexto` con la evaluación (Fase 7) |
| D5 | Base de verificaciones anteriores | Reutilización **30 días**, **7 días** si fue `insuficiente`. **Solo coincidencia exacta**: sin umbral de similitud (Fase 3, [BASE_AFIRMACIONES.md](BASE_AFIRMACIONES.md)) | — |
| D6 | Cobertura | **Todos** los análisis, con orden: discrepancias, nivel alto, resto | — |
| D7 | Sitios de verificación en la búsqueda | **Permitidos** en producción; excluidos al evaluar, midiendo el efecto aparte | — |
| D8 | Ubicación del LLM | **Equipo aparte por red**, con `LLM_BASE_URL` y clave de API | Cómo se conectan los dos equipos (red local u otra). La llamada con clave se comprobó solo en `127.0.0.1` |

| D9 | Análisis anteriores a la migración | **Solo los nuevos**; los existentes quedan `sin_verificar` | — |
| D10 | Mismo texto analizado varias veces | **Reutilizar** la verificación vigente con el mismo `hash_texto` | — |
| D11 | Reintentos | **3 intentos** con espera creciente de **1, 5 y 15 minutos**; luego `fallida` con su causa (confirmado en la Fase 5) | — |
| D12 | Base de datos de desarrollo | **Proyecto Supabase de desarrollo aparte**; el de Orlando solo recibe 008 cuando esté probada | Crear el proyecto en la Fase 0 |

| D13 | Estructura de la evaluación | **Ajuste + prueba final**, esta última abierta una sola vez | — |
| D14 | Evidencia al evaluar | **En vivo + congelada** (5.3) | — |
| D15 | Tamaño del conjunto | **80 casos**, 20 por conclusión (40 ajuste y 40 prueba final) | De dónde salen los casos concretos, al construirlo (Fase 7) |
| D16 | Umbrales de aceptación | **0 URL inventadas, citas válidas ≥ 95 %, F1 macro por encima de dos referencias** | Cifra mínima de F1 macro: tras el ajuste y antes de la prueba final |

D3 a D7 estaban asignadas a Orlando en el borrador anterior: se registran aquí como decididas en esta revisión y conviene que él las confirme antes de implementar.

## 5. Evaluación de la verificación

La calidad no se da por buena: se mide con un conjunto propio, **separado** del de clasificación.

### 5.1. Reglas

1. **No se usa** la prueba congelada de `comun_v1` (FalleDesinfo incluido): esa se abre una sola vez y para otro propósito ([01_PLAN_COMUN.md](../mejora_modelos/01_PLAN_COMUN.md), regla 3).
2. **Dos conjuntos separados (D13):** uno de **ajuste**, con el que se afinan instrucciones, tope de afirmaciones y regla de conclusión, y otro de **prueba final**, que se abre **una sola vez**, al final, y no se usa para elegir nada.
3. Nada se decide mirando la prueba final. Si algo se cambia después de abrirla, esa prueba deja de ser limpia y el informe lo dice.
4. Los umbrales se fijan antes de abrir cada conjunto (5.6).

### 5.2. El conjunto `verificacion_v1`

- **Tamaño (D15):** 80 casos, **20 por conclusión** (`respaldada`, `contradicha`, `fuera_de_contexto`, `evidencia_insuficiente`): 40 de ajuste y 40 de prueba final, con **10 por conclusión** en cada uno.
- **Unidad:** el caso completo, como lo recibiría la extensión: un texto de al menos 100 tokens (mismo mínimo que el análisis) y la conclusión esperada. Cada caso guarda además la fecha del hecho o del texto y, si se conocen, las afirmaciones centrales esperadas.
- **De dónde salen las etiquetas:**
  - `contradicha`, `fuera_de_contexto` y `evidencia_insuficiente`: verificaciones publicadas en español por medios de verificación, con el texto original que verificaron. Los veredictos de cada medio se traducen a las cuatro conclusiones con una tabla de equivalencias escrita antes (por ejemplo, «falso» → `contradicha`; «engañoso» o «sin contexto» → `fuera_de_contexto`; «no se puede comprobar» → `evidencia_insuficiente`).
  - `respaldada`: noticias en español cuyo contenido central confirman varias fuentes independientes, con las fuentes anotadas.
  - Una persona revisa cada etiqueta y la equivalencia aplicada; las dudosas se descartan.
- **Sin fugas:** los casos del mismo hecho o evento van **juntos** en ajuste o en prueba, nunca repartidos. No se usan textos de `comun_v1`.
- **Cuidado con el tiempo:** una verificación publicada hace meses puede no coincidir con lo que hoy muestra la web. Cada caso lleva la fecha y los casos cuya evidencia cambió se marcan o se descartan en la revisión.
- **Archivos:** carpeta `datasets/verificacion_v1/` (ignorada por Git, igual que `comun_v1/`) con los casos, la tabla de equivalencias y un `manifest.json` con SHA-256 de cada archivo. Lo que sí se versiona es el script que lo construye y las instrucciones.

### 5.3. Evidencia: en vivo y congelada (D14)

| Modo | Cómo corre | Para qué |
| --- | --- | --- |
| **En vivo** | Búsqueda y descarga reales en el momento | Medir el sistema como funcionará: extremo a extremo |
| **Congelado** | La primera corrida guarda las páginas recuperadas (con su hash); las demás leen esa copia | Comparar un cambio de instrucciones o de modelo en igualdad de condiciones |

- La copia guardada es solo local y no se publica ni se sube a Git.
- En ambos modos se **excluyen los dominios de los medios de verificación** usados para etiquetar, porque si no el sistema encontraría la respuesta en el propio verificador. En producción se permiten (D7); el efecto de permitirlos se mide aparte, en el conjunto de ajuste.

### 5.4. Referencias de comparación

Un acierto solo significa algo frente a algo. Se miden dos referencias con los mismos casos:

- **A. Siempre `evidencia_insuficiente`:** lo que haría un sistema que nunca se atreve.
- **B. LLM sin búsqueda:** el mismo modelo y el mismo esquema, juzgando solo con lo que sabe, sin evidencia externa. Mide cuánto aporta realmente la búsqueda.

### 5.5. Métricas

- Acierto de la conclusión: global y por clase, **F1 macro** y matriz de confusión. Se destaca el error más grave: decir `respaldada` cuando lo esperado era `contradicha`.
- **Tasa de citas válidas** (la cita existe en la fuente citada) y **tasa de URL inventadas** (0 por diseño).
- Porcentaje de casos que terminan en `evidencia_insuficiente`.
- Acuerdo entre la conclusión y el resultado rápido: solo informativo, no es una medida de acierto.
- Duración por caso (media y percentil 90) y fallas por tipo (LLM, búsqueda, salida inválida, tiempo).
- Con 40 casos por conjunto, cada cifra se reporta con el **número de casos** y su intervalo de incertidumbre, no solo como porcentaje: son resultados orientativos.

### 5.6. Umbrales de aceptación (D16)

| Criterio | Umbral |
| --- | --- |
| URL inventadas | **0** |
| Citas válidas | **≥ 95 %** |
| F1 macro de la conclusión | **Mayor que la referencia A y que la referencia B**, medido en la prueba final |
| Cifra mínima de F1 macro | Se fija **después** de ver el conjunto de ajuste y **antes** de abrir la prueba final, y se anota en la sección 8 |

### 5.7. Procedimiento

1. Construir `verificacion_v1`, revisar etiquetas y congelar el manifiesto.
2. Correr en el conjunto de **ajuste**, en vivo y congelado, con las dos referencias.
3. Ajustar y repetir en modo congelado; cada cambio queda con su `version_prompts`.
4. Fijar la cifra mínima de F1 macro (5.6) y anotarla.
5. Abrir la **prueba final una sola vez**, en vivo, y medir.
6. Escribir el informe en `docs/llm/` con el estilo de [05_PRUEBA_CONGELADA.md](../mejora_modelos/05_PRUEBA_CONGELADA.md), incluidos los errores que no se corrigieron.

Cada corrida registra `version_prompts`, `modelo_llm`, proveedor de búsqueda, fecha y modo (en vivo o congelado).

## 6. Fases de implementación

Cada fase termina con algo que se puede ejecutar y comprobar. El tamaño es relativo (S ≈ medio día, M ≈ 1–2 días, L ≈ 3+ días) y es una estimación, no un compromiso.

### Fase 0 — Entorno y preparación (S)

- Usar `backend/.venv` (ya existe y tiene lo necesario para arrancar la API) y comprobar que la API arranca con él; el README describe `bilstm/.venv` + `backend/.deps`, que aquí no existen.
- Crear un proyecto Supabase de desarrollo propio (D12), aplicar las migraciones 001–007 y comprobar que la web actual funciona (la verificación se ve «Aún no disponible»).
- Confirmar si el servidor LLM elegido (D2) se instala y usa la 5060 con CUDA en este equipo y con Python 3.14.
- **Se cierra cuando:** las pruebas existentes pasan (`backend.tests.test_web_platform`, `datos_comunes`, frontend y web) y el servidor LLM responde una petición de prueba.

### Fase 1 — Servidor LLM y cliente (M)

- Descargar las dos variantes candidatas (D1), servirlas con `llama-server` (D2) y medir en cada una: memoria usada, velocidad, contexto máximo estable y duración de una extracción típica.
- `services/llm_client.py` con esquema forzado, tiempos máximos y errores diferenciados; pruebas con un servidor simulado.
- Comprobar la conexión entre el equipo del LLM y el del backend (D8), con clave de API.
- **Se cierra cuando:** el cliente devuelve JSON válido contra un esquema de afirmaciones en un texto real, se elige la variante del modelo y se anotan las mediciones para fijar límites reales.
- **Estado (15 nov 2026):** cumplido, salvo la conexión entre los dos equipos de D8 (probado solo en `127.0.0.1`). Resultados y límites medidos en [MEDICIONES_LLM.md](MEDICIONES_LLM.md).

### Fase 2 — Datos y cola (M)

- Migración `008` y su reversión; probarla aplicar → revertir → aplicar.
- Repositorio: encolar, reclamar (con el orden de D6), copiar, completar, fallar y reintentar; `POST /analisis` encola sin hacerlo fallar; barrido de análisis sin fila posteriores a `VERIFICATION_DESDE` (D9).
- Trabajador vacío que solo mueve el estado (`pendiente → en_proceso → completada` con un resultado fijo de prueba).
- **Se cierra cuando:** crear un análisis desde la extensión deja una fila `pendiente` que el trabajador recoge una sola vez (comprobado con dos procesos a la vez), y que tras un corte vuelve a la cola al vencer la reserva.
- **Estado (15 nov 2026):** cumplido en el Supabase de desarrollo. La migración `008` se aplicó, se revirtió y se volvió a aplicar; 43 comprobaciones contra la base (orden de D6, reserva vencida, 3 intentos, falla con espera creciente, copia con su vigencia, barrido y 12 casos con dos procesos a la vez, 6 para cada uno, sin repetir ninguno) y un recorrido por la API (`POST /analisis` → `pendiente` → `en_proceso` → `completada` con 1 intento; el mismo texto se copia). Hay 26 pruebas nuevas en `backend/tests/test_verification_queue.py`. Detalles a tener en cuenta:
  - La prueba por la API cazó un fallo de la primera versión de la 008: una clave foránea en `copiada_de` rompía la web pública (PGRST201). Está corregida y tiene su prueba.
  - La cola y el encolado están apagados salvo `VERIFICATION_ENABLED=true`. El resultado que guarda el trabajador es un texto fijo de prueba, marcado `prueba-fase-2`: no se debe encender donde el público vea los resultados hasta las fases 3 a 5.
  - La reserva dura 600 s y las esperas entre reintentos (60, 300 y 900 s) son provisionales; se ajustan en la Fase 5.
  - Antes de aplicar la 008 en el proyecto de Orlando hay que coordinarlo con él.

### Fase 3 — Extracción y base de verificaciones anteriores (M)

- Instrucciones de extracción versionadas; validación y reescritura de afirmaciones.
- **Ya adelantado (15 nov 2026):** `backend/services/verification/prompts.py` (`extraccion-v1`) y `claims.py` (`extract_claims`, con la comprobación determinista de cifras y nombres). Lo medido y lo que no se arregló (atribuciones, listas vacías en noticias falsas) está en [MEDICIONES_LLM.md](MEDICIONES_LLM.md), 3.5.
- Tabla `afirmaciones_verificadas` (migración 008), funciones de búsqueda y guardado (migración 009) y `known_claims.py`: consulta por coincidencia exacta y guardado al terminar. Se descartan también las afirmaciones que dependen del texto («esta noticia», «dicho país»).
- **Se cierra cuando:** para un conjunto de textos de prueba se obtienen afirmaciones verificables razonables (revisadas a mano) y una afirmación repetida se reutiliza de la base.
- **Estado (15 nov 2026):** cumplido en el Supabase de desarrollo (migración 009 aplicada), con una desviación del plan: **solo coincidencia exacta**, sin búsqueda por similitud. Se midió con 128 paráfrasis y 148 + 164 cambios de un solo dato: con 0,80 solo se reutiliza el 2 % de las paráfrasis y pasan 42 y 45 cambios de un dato; con 0,95 pasan 1 y 3 y se reutiliza el 0 %. 23 comprobaciones contra la base y 31 pruebas nuevas. Detalle, ejemplos y el anexo de afirmaciones para revisar: [BASE_AFIRMACIONES.md](BASE_AFIRMACIONES.md). La revisión «a mano» de las afirmaciones la hice yo sobre 7 textos; falta la de una persona del equipo.

### Fase 4 — Búsqueda, descarga y juicio (L)

- `SearchProvider` y el proveedor elegido (D3); `fetch.py` con todas las defensas de 4.6 y sus pruebas (incluidas direcciones privadas y redirecciones a ellas).
- Selección de pasajes; juicio por afirmación con las comprobaciones de cita y URL.
- **Se cierra cuando:** una afirmación real recibe veredicto con cita válida, una afirmación sin evidencia recibe `insuficiente`, y un texto con instrucciones ocultas no altera el resultado.
- **Estado (15 nov 2026):** código y pruebas hechos (`search.py`, `fetch.py`, `passages.py`, `judge.py`, `pipeline.py`, `untrusted.py`; 121 pruebas nuevas, 255 en el backend). **Medido con Tavily; Brave pendiente de su clave, así que D3 sigue abierta.** Detalle en [BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md):
  - Búsqueda real (Tavily, 22 afirmaciones de respuesta conocida): 19 bien, **0 falsos `apoyada`** y ninguna `apoyada` o `contradicha` sin fuente citada; de 4,6 a 15 s por afirmación de punta a punta.
  - La descarga funciona con 14 noticias reales (0,2 a 1,4 s) y con todas las defensas probadas, también contra redirecciones a direcciones privadas. Redes sociales y video se excluyen de la descarga: no entregan texto.
  - Juicio con Wikipedia y noticias (29 afirmaciones): 23 bien y 0 falsos `apoyada`; el orden «veredicto antes que cita» y la guarda de nombres y cifras se adoptaron tras medirlos. `fuera_de_contexto` es poco fiable con este modelo y se afina en la Fase 7.
  - Órdenes ocultas: sin defensa, una noticia con una orden dejaba la extracción en 0 afirmaciones (3 de 3); con el filtro, 54 de 54 pruebas bien. El filtro detecta solo 7 de 16 órdenes nuevas: es una defensa parcial.
  - Hallazgo para decidir: los términos de Brave prohíben guardar resultados y usarlos para evaluar modelos de IA, lo que parece chocar con guardar las fuentes y con la evaluación de la Fase 7. Los de Tavily no lo dicen en lo que se leyó.

### Fase 5 — Conclusión, resumen y trabajador completo (M)

- Regla de conclusión (D4), redacción del resumen, límites por caso, reintentos (3, con espera creciente) y pérdida controlada (`fallida` con causa).
- Trabajador conectado al `lifespan` de la API, con `VERIFICATION_ENABLED` y pausa.
- **Se cierra cuando:** un análisis nuevo llega a `completada` por sí solo en el equipo de desarrollo y un fallo del LLM o de internet lo deja `fallida` o reintentando, sin afectar a la API.
- **Estado (15 nov 2026):** cumplido, con un límite importante de calidad. Código y pruebas hechos (`conclusion.py`, `case.py`, trabajador con pausa, arranque en el `lifespan`; 34 pruebas nuevas, 289 en el backend). Detalle en [CONCLUSION_Y_TRABAJADOR.md](CONCLUSION_Y_TRABAJADOR.md):
  - Recorrido real por la API (Supabase de desarrollo, LLM y Tavily): 4 análisis creados desde `POST /analisis` llegaron solos a `completada` al primer intento, 30 a 40 s por caso con 3 o 4 afirmaciones buscadas (6 s si ya estaban en la base); la API respondió en menos de 1 s mientras tanto. Con el LLM caído, `POST /analisis` y `/salud` respondieron con normalidad y el caso quedó `pendiente` con `llm_no_disponible` y su espera.
  - **Calidad:** de los 3 casos normales, la conclusión acertó 1 y falló 2 (una cierta dada por `contradicha` por un error tipográfico de una fuente; una noticia inventada dada por `contradicha` porque la extracción dejó una afirmación sin decir de qué se trata y el juez la contradijo con otra noticia). Con la regla del plan una sola afirmación mal juzgada decide el caso. No se cambió la regla: el usuario decidió dejar su ajuste a la evaluación de la Fase 7 (el documento lista 5 ajustes candidatos).
  - Reintentos: se mantienen las esperas de 1, 5 y 15 minutos (D11). La reserva (600 s) cubre el caso más largo (300 s) con margen.
  - Una orden escondida en el texto se quitó antes de extraer y no cambió el resultado.
  - La pausa existe en el trabajador (en memoria); el interruptor del panel es de la Fase 6.

### Fase 6 — Web y panel (S–M)

- Endpoints de administración de 4.7; vista de estado, botón de reintento y pausa.
- Revisar en la web pública y en el panel: lista con filtro `verificacion`, detalle con afirmaciones y fuentes, conteo en la portada, estados `pendiente`/`en_proceso`/`fallida`.
- **Se cierra cuando:** los cuatro estados y las cuatro conclusiones se ven bien en la web con datos reales y el filtro por conclusión devuelve los casos correctos.
- **Estado (15 nov 2026):** cumplido. Detalle en [WEB_Y_PANEL.md](WEB_Y_PANEL.md):
  - Backend (27 pruebas nuevas, 316 en total): `GET /admin/verificacion`, `POST /admin/casos/{id}/verificacion/reintentar`, `POST /admin/verificacion/pausar` y `/reanudar`, filtro `verificacion` en `/admin/casos` (conclusiones y estados de la cola) y `llm` en `GET /salud` sin cambiar `ok`/`degradado`. Sin migración nueva.
  - Web (7 pruebas nuevas, 16 en total): bloque de la cola con pausa y reanudar en el tablero del panel, etiqueta del estado en la lista de casos, seguimiento y botón de reintento en el detalle, y el panel «Verificación web» con el veredicto de cada afirmación y las fuentes con su cita (ancho completo).
  - Con datos reales del Supabase de desarrollo, el LLM y el navegador (escritorio y móvil): los filtros por conclusión y por estado devuelven exactamente los casos de la tabla; se vieron las cuatro conclusiones y los estados `pendiente`, `en_proceso` y `fallida`; pausar y reanudar funcionan; reintentar un caso fallido lo llevó solo hasta `completada`. Para ver todas las conclusiones se sembraron cinco casos marcados `prueba-fase-6` con afirmaciones y fuentes reales de la Fase 5; `respaldada` y `fuera_de_contexto` casi no salen del LLM con la regla actual.
  - Desviaciones: `seguimiento_verificacion` y el filtro por estado en el panel (el plan no los nombra; sin ellos no se ve la causa de una falla), y reintentar también adelanta un caso `pendiente`. Se corrigió además el plural del resumen de plantilla de la Fase 5.
  - Queda: la pausa no persiste al reiniciar la API; los textos de la portada y `web/README.md` siguen diciendo que la verificación es «próximamente» (se cambian al encenderla, Fases 7 y 8); el panel no se probó con una cuenta de administrador real (se usó una cuenta de prueba solo en el proceso de prueba).

### Fase 7 — Evaluación y ajuste (L)

- Construir `verificacion_v1` (80 casos) y correr las referencias A y B y el sistema en el conjunto de ajuste, como indica 5.7.
- Ajustar instrucciones, tope de afirmaciones y regla de conclusión **solo** con el conjunto de ajuste; cada cambio queda con su `version_prompts`.
- Fijar la cifra mínima de F1 macro, abrir la prueba final una sola vez y medir.
- **Se cierra cuando:** se cumplen los umbrales de 5.6 en la prueba final y el informe de resultados (`docs/llm/` con el mismo estilo que `05_PRUEBA_CONGELADA.md`) queda escrito, incluidos los errores que no se pudieron corregir.

### Fase 8 — Cierre y documentación (S)

- Prueba de recorrido completo: extensión → análisis rápido → verificación → web → revisión (incremento 3).
- Actualizar `backend/README.md` (rutas, variables, arranque del servidor LLM), `backend/docs/ESTADO_ACTUAL.md`, `docs/DISENO_FISICO_BASE_DATOS.md`, `docs/DICCIONARIO_DATOS_SCANTRUE.md`, `docs/DIAGRAMA_CLASES_UML.md` y el README de `web/` con lo nuevo.
- **Se cierra cuando:** una persona que no escribió el código puede levantar todo siguiendo la documentación.

## 7. Pruebas

| Nivel | Qué se prueba | Dónde |
| --- | --- | --- |
| Unitarias | Esquemas, regla de conclusión, normalización de afirmaciones, validación de citas, filtros de URL (SSRF), cliente LLM con servidor simulado | `backend/tests/` (mismo estilo que `test_web_platform.py`: sin Supabase ni pesos) |
| Cola | Reserva única con dos trabajadores, vencimiento, reintentos, pausa | Pruebas con repositorio simulado y comprobación manual en Supabase |
| Seguridad | Texto con instrucciones, redirección a red privada, página enorme, JSON roto del LLM | Casos fijos de prueba |
| Integración | Análisis real → `completada` con LLM y búsqueda reales | Guion `verificar_flujo.py` ampliado |
| Interfaz | `presentVerification` con los cuatro estados y listas vacías | `web/tests/presentation.test.js` |
| Evaluación | Sección 5 | Informe de la Fase 7 |

## 8. Criterios de aceptación del incremento

Funcionales (todos obligatorios):
1. Crear un análisis desde la extensión no se vuelve más lento ni falla si el LLM, la búsqueda o la cola no están disponibles.
2. Todo análisis creado después de aplicar la migración 008 recibe una fila de verificación y llega a un estado final (`completada` o `fallida` tras 3 intentos) sin intervención. Un texto repetido reutiliza la verificación vigente.
3. Cada conclusión se acompaña de afirmaciones y de fuentes con enlace real descargado por el backend; no hay conclusión `respaldada` o `contradicha` sin al menos una fuente con cita válida.
4. La web pública y el panel muestran el estado, la conclusión, el resumen, las afirmaciones y las fuentes, y el filtro `verificacion` funciona.
5. El administrador puede ver la cola, reintentar un caso y pausar la verificación.
6. Las migraciones se aplican y se revierten sin perder datos de los incrementos 1 y 3.

Calidad (medida en la prueba final de `verificacion_v1`, sección 5):
- URL inventadas: **0** · Citas válidas: **≥ 95 %** · F1 macro: **mayor que las referencias A y B** y que la cifra mínima fijada tras el ajuste: _por definir_ · Duración por caso (p90): _se anota al medirla en la Fase 1; sin umbral hasta entonces_.

## 9. Riesgos

| Riesgo | Efecto | Respuesta |
| --- | --- | --- |
| Un LLM de 4B se equivoca al juzgar o rompe el formato | Conclusiones erróneas | Esquema forzado, comprobación de citas, regla determinista para la conclusión, reserva de `evidencia_insuficiente` ante la duda y evaluación antes de publicar |
| La búsqueda no devuelve fuentes útiles en español | Muchos `evidencia_insuficiente` | Medirlo en la Fase 7; ajustar consultas; considerar otro proveedor (D3) |
| Verificar cuesta más que lo que llega (un caso a la vez) | Cola creciente | Prioridad por discrepancia (D6), límites por caso, métricas de cola en el panel |
| La GPU se necesita para QLoRA (4B) | Choque de uso | Pausa del trabajador (4.7); la cola se conserva |
| Contenido hostil en páginas o en el texto | Manipulación del modelo o ataques de red | Sección 4.6 |
| Fuga entre evaluación y búsqueda (los verificadores aparecen en los resultados) | Exactitud inflada | Exclusión de dominios al evaluar (D7) |
| El proveedor de búsqueda cambia condiciones o falla | Verificación detenida | Interfaz `SearchProvider` y fallo controlado (`fallida` con causa) |
| La base de verificaciones anteriores propaga un error | El error se repite | Vida útil, marca `origen: base_anterior` y posibilidad de borrar una entrada desde el panel (a evaluar en la Fase 7) |
| Python 3.14 sin soporte en alguna librería | Bloqueo de instalación | Servidor LLM como proceso aparte (4.2) y comprobación temprana en la Fase 0 |

## 10. Dependencias con otros incrementos

- **Incremento 1 (hecho):** web y panel, ya preparados para mostrar la verificación.
- **Incremento 3 (hecho en código):** la evidencia de una verificación puede sugerirse como evidencia de la revisión; no entra en este incremento salvo que se pida.
- **Incremento 4B:** necesita la pausa de la Fase 6 y el servidor LLM de la Fase 1.
