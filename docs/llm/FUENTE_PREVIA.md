# Fuente previa y límites por caso (cambio posterior a la Fase 6)

**Fecha:** 15 nov 2026. **Estado:** código y pruebas hechos, **sin commit**. La API real de Google se probó con 3 afirmaciones conocidas (sección 7): responde y sus campos coinciden con la documentación, y lo que devuelve se descarga y entrega pasajes. El recorrido completo (LLM, Google y Tavily reales) se probó con 5 afirmaciones y con un caso de 3 (sección 9): con una muestra pequeña, el resultado es orientativo y deja un hallazgo que hay que decidir. Antecedentes: [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md) (D3, D5, D7), [BUSQUEDA_Y_JUICIO.md](BUSQUEDA_Y_JUICIO.md) y [EVALUACION_VERIFICACION.md](EVALUACION_VERIFICACION.md).

## 1. Qué cambia

| Qué | Antes | Ahora | Dónde |
| --- | --- | --- | --- |
| Afirmaciones por noticia | 5 | **3** | `MAX_CLAIMS` en [verification.py](../../backend/schemas/verification.py) y el prompt de extracción |
| Consultas por afirmación | 2 | **1** (con `VERIFICATION_MAX_QUERIES=2` se vuelve a 2) | `queries_per_claim` en [config.py](../../backend/core/config.py) |
| Páginas por afirmación | 4 | 4 (sin cambio) | `pages_per_claim` |
| Fuente previa | no existía | **Google Fact Check Tools**, antes de la búsqueda web, con una consulta corta (sección 8) | `FactCheckSearch` en [search.py](../../backend/services/verification/search.py) y `verify_claim` en [pipeline.py](../../backend/services/verification/pipeline.py) |
| Prompt de extracción | `extraccion-v1` | **`extraccion-v2`** | [prompts.py](../../backend/services/verification/prompts.py) |

Efecto esperado en gasto: hasta **3 búsquedas de Tavily por noticia** (antes unas 9) y hasta **12 páginas** descargadas (antes 20), más hasta 3 consultas a la fuente previa. Cuando la fuente previa no basta hay un juicio más del LLM por afirmación.

## 2. Cambio de comportamiento que hay que medir: «las 3 más importantes»

`extraccion-v2` pide como máximo 3 afirmaciones, **«las más importantes: las más centrales de la noticia y que se puedan comprobar con datos concretos»** (definición dada por quien pidió el cambio). Antes el modelo devolvía hasta 5 sin criterio de prioridad.

Esto **no es solo un valor**: cambia qué se verifica. Riesgos a medir en la Fase 7 con el conjunto de ajuste, comparando `extraccion-v1` y `v2` con los mismos casos:

- Una afirmación contradicha que antes era la 4.ª o la 5.ª ahora no se revisa (el caso puede salir `respaldada` o `insuficiente` en vez de `contradicha`).
- Con menos afirmaciones `respaldada` es más alcanzable (hay menos que puedan fallar), y la conclusión depende más de cada una.
- El modelo puede elegir mal cuáles son las centrales; no hay forma de comprobarlo sin casos con la afirmación central señalada (`afirmaciones_centrales` está en el formato de `verificacion_v1`, vacío por ahora).

Cada resultado guarda su `version_prompts`, que ya incluye `extraccion-v2`, así que las corridas quedan etiquetadas.

## 3. La fuente previa

**Qué es.** La API [claims:search](https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search) busca afirmaciones ya revisadas por medios de verificación y devuelve, por cada una, el enlace del artículo de verificación (`claimReview.url`), su título, el medio y una calificación textual. No devuelve el texto del artículo.

**Cómo se usa** (en `verify_claim`, por afirmación):

1. El LLM propone la consulta de la web como siempre (sin cambios). **A la fuente previa va otra, más corta**: una segunda llamada al LLM (`consulta-corta-v1`) que pide 2 o 3 palabras clave, los nombres propios y el hecho central. Si da 0 resultados se pasa directo a la web: se probó una consulta aún más corta (el nombre propio principal) y se **quitó** porque solo añadía ruido (sección 8). La llamada extra al LLM tarda unos 0,6 s por afirmación (sección 8).
2. Se consulta la fuente previa (`languageCode=es`, `pageSize` = resultados por consulta) y se descargan hasta **2 páginas** (`previous_pages`) de las que devuelve, con las mismas defensas de red y límites que cualquier página.
3. Se eligen los pasajes y el juez da un veredicto con cita literal, como siempre.
4. **Solo si el veredicto es «apoyada» o «contradicha» se termina ahí y no se busca en Tavily** (`origen_busqueda = "verificadores"`; `PREVIOUS_STOPS` en `pipeline.py`). «Insuficiente» y «fuera_de_contexto» **no** detienen la búsqueda (regla del 15 nov 2026, ver la sección 9).
5. Si no hay resultados, no hay páginas con texto, la API falla, o el juez dice «insuficiente» o «fuera_de_contexto», se busca en Tavily como antes. **El juicio final usa solo las páginas de la web**, con el tope completo de 4: las de la fuente previa se descartan (opción A de la sección 9.1: mezclarlas empeoraba el veredicto cuando eran de otra afirmación). Si la web devuelve una dirección que ya se descargó de la previa, se reutiliza sin bajarla otra vez y cuenta como página de la web. Con la fuente previa que no basta se pagan, por tanto, hasta 2 descargas y un juicio de más. Se anota `origen_busqueda = "verificadores+web"` o `"web"`.

**Qué no hace:**

- **No usa la calificación de la API** (`textualRating`) como evidencia ni la copia a los resultados: el veredicto lo sigue dando el juez a partir del texto descargado, con la cita comprobada.
- Una falla de la fuente previa (clave rechazada, cupo, red) **no hace fallar la afirmación**: se registra una advertencia (con el código del error, sin consulta ni clave) y se sigue con la web. Solo la falla de la web propaga el error, como antes.
- «Relacionado» no lleva umbrales propios: se decide por el juez. Si la verificación encontrada no habla del hecho, lo esperable es que el juez diga «insuficiente» o «fuera_de_contexto»: en los dos casos se busca en la web.

## 4. Cómo encaja

- **`SearchProvider`:** `FactCheckSearch` implementa la misma interfaz y devuelve `SearchResult`, así que descarga, pasajes y comprobación de la cita no cambian. El único cambio de lógica está en `verify_claim` (parámetro opcional `previous_search`; sin él todo funciona exactamente como antes).
- **Comprobación de la cita:** igual que siempre. La fuente solo cuenta si el backend descargó la página y la cita aparece literal en uno de sus pasajes; el título o la afirmación que devuelve la API no son evidencia.
- **Caché de D5:** se consulta **antes** que cualquier búsqueda y no cambia. Guarda veredicto y fuentes sin distinguir quién encontró la evidencia, así que **no hace falta migración**. Con `extraccion-v2` las afirmaciones pueden redactarse distinto y reutilizarse menos al principio (la coincidencia es exacta, y la versión de las instrucciones no forma parte de la clave).
- **Evaluación y D7:** la fuente previa solo devuelve medios de verificación, y al evaluar esos dominios se excluyen: con `FACT_CHECKERS` y los dominios del caso, **la fuente previa no aporta resultados en la evaluación y todo cae a Tavily**. El ejecutor de la Fase 7 no la enciende. Un resultado de D7 («medir el efecto aparte») **no se puede obtener honestamente con `verificacion_v1` tal como está**: las etiquetas de 60 de los 80 casos salen de esos mismos medios, así que dejarla activa daría la respuesta. Solo la tanda `respaldada` (etiqueta por fuentes independientes) permitiría medirla sin fuga.
- **Privacidad:** a Google salen solo las consultas que propone el LLM a partir de la afirmación (limpias de direcciones y correos), nunca la URL, el texto completo ni la identidad del usuario; la clave va en una cabecera, no en la dirección, y no se escribe en los registros.

## 5. Configuración

| Variable | Qué hace |
| --- | --- |
| `FACTCHECK_API_KEY` | Clave de la API. **Sin ella la fuente previa no se usa** y el sistema se comporta como antes. |
| `FACTCHECK_TIMEOUT` | Segundos por consulta (10 por omisión, entre 0 y 120). Un valor inválido impide arrancar la cola, como los demás ajustes de la verificación. |
| `VERIFICATION_MAX_QUERIES` | Consultas por afirmación (1 o 2; por omisión 1). |

Para activarla: habilitar la **Fact Check Tools API** en el proyecto de Google Cloud, crear una clave de API y ponerla en `backend/.env.desarrollo` (ignorado por Git; nunca en un archivo versionado ni en el chat). Las variables están documentadas, sin valores, en [.env.example](../../backend/.env.example).

### Cómo apagarla

Decisión del usuario (15 nov 2026): **la fuente previa se mantiene** y se apaga **vaciando `FACTCHECK_API_KEY`**; no se añade un interruptor aparte (`FACTCHECK_ENABLED`, que serían unas 15 líneas y no se hará por ahora).

1. **Vaciar o quitar** `FACTCHECK_API_KEY` en el entorno del proceso de la API.
2. **Reiniciar la API.** La configuración se lee al arrancar (`build_case_verifier`) y el trabajador no la relee en caliente.
3. **Comprobar** en el registro de arranque la línea «Sin fuente previa (FACTCHECK_API_KEY vacía): solo búsqueda web».

**Qué pasa al apagarla:** el sistema vuelve al camino anterior a la fuente previa. No hay llamada al LLM para la consulta corta ni llamada a Google, y `origen_busqueda` es siempre `web`. Está cubierto por la prueba `test_la_fuente_previa_solo_existe_con_su_clave`.

**El detalle del entorno:** el código carga el archivo de entorno con `load_dotenv(override=False)`, que **no pisa una variable que ya esté definida en el entorno del proceso**. Si `FACTCHECK_API_KEY` llega desde el entorno real (variable del sistema, del servicio o de la terminal desde la que se arranca) y no solo desde el archivo, vaciarla en el archivo **no basta**: hay que vaciarla también allí. En el equipo de desarrollo la clave está en `backend/.env.desarrollo` y se carga en el entorno al arrancar a mano, así que hay que vaciarla en ese archivo **y** arrancar con una terminal que no la tenga exportada de antes. Al vaciarla se pierde dónde estaba guardada; si se quiere volver a encender, la clave hay que tenerla a mano en otro sitio.

## 6. Pruebas

- **Backend: 363 → 388 pruebas** (25 nuevas), todas pasan. Nuevas: 6 del proveedor (parámetros, clave en cabecera, exclusión de dominios, sin copiar la calificación, errores sin la clave, configuración), 10 de `verify_claim` con fuente previa (basta; no basta y se juzga con todo; sin resultados; falla de la API; falla de la web; tope de páginas; página repetida; dominios excluidos; sin nada; cita inventada), 2 de consultas y de `select_results`, 3 del verificador de caso y de su construcción, 2 de la regla de suficiencia («contradicha» basta; «fuera_de_contexto» no) y 3 de la consulta corta (a la previa va la corta y a la web la de siempre; si la corta da 0 se pasa directo a la web sin otra consulta ni otra llamada al LLM; limpieza de la consulta).
- **Adaptadas 4:** `test_descarta_y_renumera` (usaba 4 afirmaciones y el tope es 3), `test_version_y_reglas_clave` (el prompt), y las dos de dos consultas (ahora piden `queries_per_claim=2` de forma explícita).
- **Prueba intermitente de la Fase 6, arreglada el 15 nov 2026:** `test_verification_admin.RepositoryTests.test_cuenta_por_estado_y_promedia_la_duracion` miraba `repo.requests[-1]` (la última petición) como si fuera la de las duraciones, pero `verification_stats` hace sus cinco consultas a la vez en hilos y la última registrada varía: con la comprobación anterior, la última no era la de duraciones en **156 de 400 ejecuciones**. Ahora la prueba busca la única petición `GET`; con eso fallaron **0 de 400** ejecuciones y 3 corridas completas seguidas pasaron. Solo cambió la prueba, no el código.

## 7. Prueba con la API real (15 nov 2026)

Con la clave en `backend/.env.desarrollo` (ignorado por Git), una consulta por afirmación escrita a mano con el estilo de las que propone el LLM, sin excluir ningún dominio, y pasando lo devuelto por `FactCheckSearch`, `PageFetcher` y `select_passages` (sin LLM ni Tavily):

| Afirmación | Consulta | Resultados | Qué se obtuvo |
| --- | --- | ---: | --- |
| La ONU prevé que toda la humanidad será chipeada antes de 2030 | `ONU chips humanidad antes de 2030` | 2 | Ecuador Chequea y Maldita.es; las 2 páginas se descargaron con texto y salieron 6 pasajes (el mejor, puntaje 10,3, repite la afirmación y dice que es falsa) |
| La NASA alertó que la Tierra perderá la gravedad durante siete segundos en agosto de 2026 | `NASA Tierra perderá gravedad siete segundos agosto 2026` | 5 | Ecuador Chequea (2), Maldita.es, EFE Verifica y Grupo Animal; las 2 primeras páginas se descargaron y dieron 6 pasajes |
| La Cámpora y Madres de Plaza de Mayo publicaron comunicados en repudio a la muerte de El Mencho | `La Cámpora Madres de Plaza de Mayo comunicado muerte El Mencho` | **0** | Nada, aunque Chequeado verificó ese hecho |

Lo que se comprobó y lo que enseñó:

- **El proveedor funciona con la API real:** HTTP 200 con la clave en la cabecera, y la respuesta tiene exactamente los campos de la documentación (`claims[].text` y `claims[].claimReview[]` con `publisher`, `url`, `title`, `reviewDate`, `textualRating` y `languageCode`). Las verificaciones que devuelve son de medios como Ecuador Chequea, Maldita.es, EFE Verifica, AFP Factual y Grupo Animal.
- **La cobertura es parcial:** la verificación de Chequeado sobre los comunicados del «Mencho» **no aparece**; con otras consultas salieron verificaciones de AFP Factual, Grupo Animal y Ecuador Chequea sobre el mismo suceso, pero no esa. Depende de qué medios publican su revisión de forma que Google la indexe. Cuando no hay nada, el sistema pasa a Tavily como está previsto.
- **Las consultas largas devuelven 0:** «El Mencho La Cámpora» y «Mencho comunicado Madres de Plaza de Mayo» dieron 0 resultados, y «Mencho» sola dio 5. La API parece exigir que casi todas las palabras de la consulta estén en el texto de la afirmación revisada. Con consultas de 4 a 12 palabras, como pide el prompt, habrá muchos casos sin resultados. **No se cambió nada** (se mide primero): una opción sería una consulta más corta para esta fuente, que obligaría a otra instrucción al LLM.
- **Sin el filtro de idioma** salen también resultados en otros idiomas (por ejemplo en árabe); `languageCode=es` los evita pero no es lo que causó los 0.
- **Lo devuelto sirve como evidencia:** las páginas de los verificadores se descargan con las defensas habituales y producen pasajes que citan la afirmación revisada. Que el artículo la declare falsa lo decide después el juez, con cita literal.

## 8. Mejora de la cobertura: consulta corta, mínima (quitada) e idioma (medición)

Pedido: (1) una consulta corta para esta fuente, (2) una más corta si da 0, (3) limitar a español. **Estado final: se mantiene (1) y (3) (ya estaba); (2) se quitó del código y de las pruebas el 15 nov 2026 a petición del usuario, y lo que sigue es el registro de la medición que lo motivó.** Se midió **antes** y **después de cada cambio**, de uno en uno, con las mismas 14 afirmaciones: las 3 de la sección 7 y 11 nuevas (7 con verificación publicada que conocemos, 4 sin ella: noticias ciertas o hechos generales). Las consultas largas son las que escribe el LLM hoy (la primera de la web); las cortas y mínimas, las que escribe el LLM con los prompts nuevos. Se guardaron para repetir las mediciones con las mismas. Se usó el LLM solo para escribir consultas (sin juez, sin Tavily).

**Cómo se juzgó «pertinente»:** el medio revisó **la misma afirmación** (mismo suceso y mismo dato), de modo que su artículo permitiría juzgarla. Mismo tema o misma persona pero otra afirmación es **no pertinente**. Lo juzgué yo a mano mirando la afirmación revisada y el título; la lista completa está en el apéndice de esta sección. Con 14 afirmaciones es una medición orientativa.

| Etapa | Afirmaciones con resultados (de 14) | Resultados | Pertinentes | No pertinentes | Con verificación encontrada (de 10) | Sin verificación pero con resultados (de 4) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Antes:** consulta larga del LLM (≈10 palabras) | 6 | 9 | 9 | 0 | **6** | 0 |
| **Cambio 1:** consulta corta (≈4 palabras) | 7 | 15 | 13 | 2 | **6** | 0 |
| **Cambio 2 (quitado):** + mínima si la corta da 0 | 13 | 41 a 45 | 13 | 28 a 32 | **6** | 3 |
| **Punto 3:** quitar el filtro de idioma (comparación) | 13 | 46 | 13 | 33 | 6 | 3 |

«Con verificación encontrada» cuenta las afirmaciones de las que se obtuvo al menos un resultado pertinente. Los resultados de la API varían un poco entre corridas (41 y 45 en dos corridas iguales).

**Cambio 1, consulta corta.** Más profundidad, no más cobertura: las mismas 6 afirmaciones con verificación de antes, pero con más resultados pertinentes cada una (NASA 3 → 5, Trump 1 → 3, ONU 2 → 2, el resto igual: 9 → 13). Se coló ruido: «Javier Milei planes sociales» devolvió 2 verificaciones de Chequeado de otras frases del presidente (2 no pertinentes). Una primera redacción del prompt devolvió consultas de 4 a 7 palabras (media 5,4); se reforzó con «nunca más de 3» y 2 ejemplos ajenos al conjunto de prueba. **Resultado final: 8 consultas de 3 palabras, 4 de 4, 1 de 6 y 1 de 7 (media 3,8)**, frente a 9,9 de las largas. El modelo no cumple siempre el máximo de 3.

**Cambio 2, mínima si la corta da 0 (quitado).** **No ayudó:** de las 7 afirmaciones sin resultados con la corta (3 con verificación publicada y 4 sin ella), 6 recibieron 5 resultados cada una y **ninguno era pertinente** (Galarreta siguió en 0): «El Mencho» devolvió verificaciones de AFP sobre otras afirmaciones del mismo suceso, «Messi» sobre partidos y fotos de otro tipo, «Lima» sobre un puente y un arzobispo, «Keiko Fujimori» sobre otros vídeos, «Colombia» sobre terremotos y «Amazonas» sobre anacondas. El resultado neto fue **+0 pertinentes y +26 a 30 no pertinentes**, y 3 de las 4 afirmaciones sin verificación pasaron a tener resultados (todos ruido). En el recorrido real esos resultados se descargarían (2 páginas por afirmación) y llegarían al juez antes de caer a Tavily: más tiempo, más gasto y el riesgo de que el juez dé un veredicto con una página que habla de otra afirmación. **Se quitó** (otra opción habría sido exigir antes que la afirmación revisada comparta varias palabras con la afirmación; no se hizo).

**Punto 3, español.** Ya estaba hecho (`languageCode=es` desde la primera versión; la API lo permite). Sin el filtro, con las mismas consultas, entre 11 y 13 de 46 resultados (24 a 28 %) no estaban en español (portugués, inglés, francés, árabe, bengalí, griego y filipino), todos no pertinentes, y los 13 pertinentes eran los mismos. **Con el filtro no se perdió ninguno.** En una de las corridas con filtro apareció 1 resultado que no era español; en las otras, ninguno.

**Lo que no cambió con ninguna consulta:** 4 de las 10 afirmaciones con verificación publicada (Mencho/Cámpora, Milei/planes sociales, Messi/Ibiza y el audio del terremoto de Lima) **no obtuvieron ningún resultado pertinente con ninguna de las consultas probadas ni con ni sin filtro de idioma**. Con estas consultas, el límite está en lo que Google indexa de los medios, no en la forma de la consulta.

### Apéndice: resultados pertinentes por etapa

Pertinentes y no pertinentes por afirmación con la consulta corta (el resto es igual o está en el texto de arriba): ONU 2 y 0, NASA 5 y 0, Mencho 0 y 0, Zelenski 1 y 0, Milei 0 y 2, Messi 0 y 0, feriado bancario 1 y 0, terremoto 0 y 0, Trump 3 y 0, Alina Manrique 1 y 0, Keiko, inflación, Amazonas y Galarreta 0 y 0. Con la mínima (ya quitada) se añadían 5 no pertinentes a cada una de Mencho, Messi, terremoto, Keiko, inflación y Amazonas; Galarreta sigue en 0 (con «Luis Galarreta»).

### Tiempo que añade la consulta corta

La consulta corta es **una llamada más al LLM por cada afirmación que se verifica** (las que ya están en la base de afirmaciones de D5 no la hacen) y va **antes** de consultar la fuente previa, así que suma tiempo directamente. Medido el 15 nov 2026 con el mismo modelo y servidor de producción (Qwen3-4B-Instruct-2507 Q8_0, `llama-server`, RTX 5060, solo en `127.0.0.1`), con las 14 afirmaciones de la medición y 3 rondas cada una (42 llamadas por fila), contando el tiempo completo de la llamada desde el backend:

| Llamada | Media | Mediana | p90 | Mín. a máx. |
| --- | ---: | ---: | ---: | ---: |
| Consulta corta, justo después de otra llamada con otra instrucción (lo normal en el recorrido real) | **0,61 s** | 0,64 s | 0,72 s | 0,35 a 0,84 s |
| Consulta corta, repetida seguida (el servidor reutiliza el prefijo de la instrucción) | 0,57 s | 0,61 s | 0,65 s | 0,33 a 0,84 s |
| Para comparar: la consulta de la web, que ya existía | 1,24 s | 1,27 s | 1,39 s | 0,92 a 1,60 s |

- **Por noticia:** con las 3 afirmaciones del tope, **unos 1,8 s de media y 2,2 s en el p90**, si ninguna estaba en la base de D5. El mensaje de la llamada son 244 tokens (la instrucción más una afirmación) y la respuesta unas pocas palabras.
- **Contexto:** es menos que la consulta de la web que ya se hace (1,24 s). En el recorrido de la Fase 5, con 3 o 4 afirmaciones buscadas, un caso tardó de 30 a 40 s, de modo que 1,8 s es un 5 % aproximado (esos casos eran con 5 afirmaciones y 2 consultas, que ya no son los límites; no se repitió el recorrido completo).
- **Lo que no se midió, y es lo que decide si compensa:** el tiempo y el gasto que **ahorra** la fuente previa cuando basta (no se busca en Tavily ni se descargan sus páginas: una búsqueda y hasta 2 páginas menos de las 4). Con esta muestra, la consulta corta no encontró ninguna afirmación más que la consulta larga (6 de 10 en ambos casos): su aporte medido es **más resultados pertinentes sobre las mismas afirmaciones** (9 a 13), no más afirmaciones resueltas. Si se prescindiera de la consulta corta y se usara la consulta de la web también para la fuente previa, se ahorrarían esos 0,6 s por afirmación con la misma cobertura, y se perderían esos resultados pertinentes adicionales.
- **Si el LLM va en otro equipo (D8):** a estos 0,6 s se suma la latencia de red de una llamada más.

## 9. Recorrido real con LLM y Tavily (15 nov 2026)

Con autorización del usuario. LLM local (Qwen3-4B Q8_0), Google Fact Check y Tavily reales. **5 afirmaciones** elegidas a mano: 2 con verificación publicada e indexada en la API (ONU y chips, NASA y gravedad), 1 con verificación publicada que la API no indexa (récord de planes sociales de Milei) y 2 sin verificación, noticias ciertas (inflación de Colombia, proclamación de Keiko Fujimori). Cada una se verificó **dos veces seguidas con `verify_claim`**, con la fuente previa y solo con la web (lo de antes), y se repitió la ronda. Después, **un caso completo** con `CaseVerifier` (extracción `v2`, verificación, conclusión y resumen) en los dos modos.

Cómo se contó: los créditos de Tavily son las búsquedas hechas (una por afirmación, 1 crédito cada una), contadas por el propio guion. El punto de uso de Tavily devolvió 136 créditos antes y después, o sea que **no sirvió para confirmarlo** (no se actualiza al momento o no cuenta estas llamadas). Los tiempos son de reloj en una sola máquina; entre repeticiones varían de 1 a 3 s, del tamaño del efecto que se busca, así que son orientativos.

| Afirmación | Qué pasó con la fuente previa | Tavily: con previa / solo web | Tiempo medio de 2 rondas: con previa / solo web | Veredicto: con previa / solo web |
| --- | --- | :---: | :---: | --- |
| ONU y chips | **bastó** (2 resultados, 1 juicio) | 0 / 1 | 5,7 s / 6,3 s | contradicha / contradicha |
| NASA y gravedad | **bastó** (5 resultados) | 0 / 1 | 4,2 s / 5,8 s | contradicha / contradicha |
| Milei, planes sociales | **«bastó» con evidencia de otra afirmación** | 0 / 1 | 4,7 s / 4,4 s | **fuera_de_contexto** / contradicha |
| Inflación de Colombia | 0 resultados, pasó a Tavily | 1 / 1 | 7,3 s / 4,5 s | fuera_de_contexto / fuera_de_contexto |
| Proclamación de Keiko Fujimori | 0 resultados, pasó a Tavily | 1 / 1 | 3,8 s / 1,6 s | insuficiente / insuficiente |
| **Total por ronda** | 3 bastaron, 2 no | **2 / 5** | 25,6 s / 22,5 s | |

**Créditos de Tavily que se ahorran.** Cuando la fuente previa basta, esa afirmación no gasta el crédito de Tavily: en esta mezcla, **3 de 5 (60 %)** por ronda. En el caso completo: 2 créditos frente a 3 (se ahorró 1 de 3).

**Tiempo.** Es menos claro:
- **Cuando la fuente previa basta** (6 pares de ejecuciones): **0,6 s menos de media** (4 más rápidas, 2 iguales o más lentas; de 3,1 s menos a 1,3 s más). Ahorra la búsqueda de Tavily y una de las 3 o 4 descargas, pero la llamada al LLM de la consulta corta (unos 0,8 s aquí) y la de Google (0,24 s de media) se pagan siempre.
- **Cuando no encuentra nada** (4 pares): **2,5 s más de media**, de los cuales unos 1,0 s son la consulta corta y la llamada a Google (la suma de lo medido por separado) y el resto es variación en las descargas de las páginas.
- **En total, con esta mezcla:** 5,1 s por afirmación con la fuente previa frente a 4,5 s sin ella (**+0,6 s, un 14 % más**). En el caso completo, 23,7 s frente a 15,6 s (una sola ejecución de cada una: 11 llamadas al LLM frente a 7, más una segunda ronda de juicio en una afirmación).

**Cuántas veces el juez da «insuficiente» y se pasa a Tavily.** De las **13 verificaciones con la fuente previa** (10 de las rondas por afirmación y 3 del caso completo):

| Qué pasó | Veces | % |
| --- | ---: | ---: |
| La fuente previa bastó y no se buscó en Tavily | 7 | 54 % |
| La fuente previa no encontró nada y se buscó en Tavily | 5 | 38 % |
| **La fuente previa devolvió páginas, el juez dijo «insuficiente» y se pasó a Tavily** | **1** | **8 %** |

El único caso del tercer tipo fue la afirmación del DANE en el caso completo: la fuente previa devolvió páginas, el juez dio «insuficiente» y, con las páginas de las dos fuentes, el juicio final siguió siendo «insuficiente». La ruta `verificadores+web` funciona de punta a punta.

**Hallazgo y decisión: una «suficiencia» falsa.** Con la afirmación de Milei, la consulta corta «Javier Milei planes sociales» devolvió dos verificaciones de Chequeado sobre **otras** frases del presidente. El juez no dijo «insuficiente»: dijo **`fuera_de_contexto`**, citando «Incorporamos a 600 mil chicos a la AUH», y como no era «insuficiente», la fuente previa «bastó» y no se buscó en Tavily. **Pasó las 5 veces que se probó** (2 rondas y 3 repeticiones aparte). Solo con la web, la misma afirmación salió `contradicha`, que es lo que dice la verificación de Chequeado de esa cifra. Es el riesgo de la sección 7 (una verificación de otra afirmación llega al juez) en la práctica: la guarda de cifras y nombres y la cita literal no lo frenaron, y `fuera_de_contexto` ya se sabía poco fiable. **Decisión del usuario (15 nov 2026): solo «apoyada» o «contradicha» detienen la búsqueda; con «fuera_de_contexto» o «insuficiente» se busca también en Tavily.** Implementada en `verify_claim` (constante `PREVIOUS_STOPS`) con 2 pruebas nuevas: «contradicha» basta, y «fuera_de_contexto» de la previa no detiene la búsqueda (el juicio final usa las páginas de las dos fuentes). Se esperaba que Milei gastara su crédito de Tavily y diera el veredicto de la web. **Se comprobó con datos reales (sección 9.1): pasa a Tavily, pero el veredicto sigue siendo `fuera_de_contexto`**, porque el juicio final mezcla las páginas de las dos fuentes.

**Caso completo (una ejecución por modo):**

| | Con fuente previa | Solo web |
| --- | --- | --- |
| Tiempo | 23,7 s | 15,6 s |
| Búsquedas en Tavily | 2 | 3 |
| Llamadas al LLM | 11 | 7 |
| Origen por afirmación | NASA: `verificadores`; Keiko: `web`; DANE: `verificadores+web` | las 3: `web` |
| Veredictos | NASA contradicha, Keiko insuficiente, DANE insuficiente | NASA contradicha, Keiko insuficiente, DANE **contradicha** |
| Conclusión | **contradicha** | **contradicha** |

La extracción `v2` eligió las 3 afirmaciones del texto. La conclusión coincide porque la de la NASA decide el caso. En la del DANE, el modo solo web dio `contradicha` con una página de `growcop.co`, para un dato que el piloto había confirmado como cierto (5,30 %): es un error del juez que no tiene que ver con la fuente previa (en las rondas por afirmación esa frase salió `fuera_de_contexto` en los dos modos), pero muestra la variación entre ejecuciones del modelo.

**Qué dice esto y qué no.** Con 5 afirmaciones elegidas a mano y 2 rondas, la fuente previa **ahorra créditos pero no tiempo**, y hubo un veredicto equivocado por una suficiencia falsa. La muestra lleva 3 afirmaciones con verificación publicada de 5: **en el tráfico real habrá muchas menos**, así que es de esperar (inferencia mía, no medida) que la fuente previa no encuentre nada la mayoría de las veces y entonces solo aporte su coste de ≈1 s por afirmación a cambio de ahorros de crédito en una minoría.

### 9.1 Confirmación con la regla nueva y datos reales (15 nov 2026)

Autorizado por el usuario. Misma configuración de la sección 9 (LLM local, Google Fact Check y Tavily reales, `verify_claim` con la fuente previa) y la regla nueva: solo «apoyada» o «contradicha» detienen la búsqueda. **Milei 3 veces; ONU y chips y NASA y gravedad una vez cada una.**

| Afirmación | Tiempo | Veredicto | Origen | Créditos de Tavily | Juicios |
| --- | ---: | --- | --- | ---: | ---: |
| Milei, repetición 1 | 7,4 s | **fuera_de_contexto** | `verificadores+web` | 1 | 2 |
| Milei, repetición 2 | 6,6 s | **fuera_de_contexto** | `verificadores+web` | 1 | 2 |
| Milei, repetición 3 | 6,3 s | **fuera_de_contexto** | `verificadores+web` | 1 | 2 |
| ONU y chips | 5,7 s | contradicha | `verificadores` | **0** | 1 |
| NASA y gravedad | 5,4 s | contradicha | `verificadores` | **0** | 1 |
| **Total de créditos de Tavily gastados** | | | | **3** | |

Los créditos son las búsquedas contadas por el guion (una por afirmación que pasó a Tavily). El punto de uso de Tavily volvió a devolver 136 antes y después, o sea que tampoco esta vez sirvió para confirmarlo.

**Lo que se confirmó:**
- **ONU y NASA siguen sin gastar Tavily** cuando la fuente previa basta (0 créditos, 1 juicio, `contradicha` con una cita literal de `ecuadorchequea.com`).
- **Milei ya pasa a Tavily** en las 3 repeticiones (1 crédito cada una, 2 juicios, 4 páginas): el `fuera_de_contexto` de la previa ya no detiene la búsqueda.

**Lo que no salió como se esperaba:** el veredicto de Milei **no** es `contradicha`, sigue siendo `fuera_de_contexto` (3 de 3), aunque la fuente citada ahora **es la verificación correcta de Chequeado** («Es falso que durante el gobierno de Javier Milei “se llegó al récord histórico de planes sociales en 2026”»). Solo con la web, esta afirmación había salido `contradicha` las dos veces de la sección 9. Cuesta unos 2,4 s más que solo con la web (6,8 s de media frente a 4,4 s): una llamada más al juez y 4 páginas en vez de 2.

**Diagnóstico, sin gastar Tavily** (la misma afirmación juzgada 3 veces con cada conjunto de páginas; el modelo dio el mismo veredicto las 3 veces):

| Páginas que ve el juez | Veredicto (3 de 3) |
| --- | --- |
| Solo la verificación correcta de Chequeado (como «solo web») | **contradicha** |
| Esa más las 2 páginas de la fuente previa (como el juicio final) | **fuera_de_contexto** |
| Solo las 2 páginas de la fuente previa | fuera_de_contexto |

O sea: **las dos páginas de la fuente previa, que hablan de otras frases de Milei, contaminan el juicio final** y le quitan la respuesta correcta que la web sí encontró. Mezclar la evidencia de las dos fuentes, que era lo que pedía la regla del usuario («busca también en Tavily»), es lo que hace que el veredicto se quede en `fuera_de_contexto`.

**Opciones que se plantearon (el usuario eligió la A, sección 9.2):**
- **A. Si la previa no basta, el juicio final usa solo las páginas de la web** (descartar las de la previa). El coste es perder la evidencia de la previa cuando sí era pertinente y solo el juez la había juzgado «insuficiente», y se pagan igual las 2 descargas y un juicio. **Elegida e implementada.**
- **B. Mantener la mezcla pero filtrar los pasajes de la previa** por pertinencia antes del juicio final. Más código y umbrales que habría que medir.
- **C. Dejarlo como está.**

Con una sola afirmación de este tipo no se puede decir cuántas veces pasa en general.

### 9.2 Opción A implementada y comprobada (15 nov 2026)

**Qué cambió.** En `verify_claim`, cuando la fuente previa no basta («insuficiente» o «fuera_de_contexto», o no hay nada), se buscan y descargan las páginas de la web con el **tope completo de 4** y el juicio final ve **solo esas**. Las páginas ya descargadas de la previa se descartan, salvo que la web devuelva la misma dirección (se reutiliza, sin bajarla otra vez). Desaparece el parámetro `skip` de `select_results`, que solo servía para el reparto anterior del tope. La consulta de la web, la regla de suficiencia y todo lo demás siguen igual.

**Pruebas (389 → 388).** La del caso Milei ahora comprueba lo pedido con dos páginas de contenido distinto: el primer juicio (sobre la previa) **sí** ve el texto de la página de la previa, y el juicio final **no** lo recibe y **sí** recibe el de la web; el veredicto final sale de la web (`contradicha`), la única fuente es la de la web y `origen_busqueda` es `verificadores+web`. Otras tres cambiaron de significado: el juicio final es solo con la web; el tope de la web es completo y las páginas de la previa no cuentan; y una dirección que la web también devuelve no se baja dos veces. Se quitó la prueba de `skip` (−1). Las 388 pasan en dos corridas completas seguidas.

**Comprobación con datos reales: Milei, una vez, con el LLM, Google y Tavily.**

| Afirmación | Tiempo | Veredicto | Origen | Créditos de Tavily | Juicios | Páginas del juicio final |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Milei | 14,5 s | **contradicha** | `verificadores+web` | **1** | 2 | 3 (todas de la web) |

- **Sale `contradicha`** y citando la verificación correcta de Chequeado («Es falso que durante el gobierno de Javier Milei “se llegó al récord histórico de planes sociales en 2026”»). Las fuentes que llegan al usuario son `chequeado.com` y una copia en `rechequeado.com` con la misma cita.
- **Créditos de Tavily gastados: 1** (la búsqueda que ahora sí se hace). El punto de uso de Tavily devolvió otra vez 136 antes y después, así que no lo confirma.
- **Tiempo:** 14,5 s, bastante más que los 6,3 a 7,4 s de la versión anterior (con la mezcla) y los 3,7 a 5,0 s de solo web. Es **una sola ejecución**; el camino ahora baja hasta 2 páginas de la previa y hasta 4 de la web (antes 4 en total), y el tiempo de las descargas varía mucho entre ejecuciones. Repetido 3 veces con el desglose por fase (sección 9.3): 10,7 s de media frente a 6,6 s solo con la web.

**Lo que no se comprobó:** ONU y NASA no se repitieron con el cambio (el camino en que la previa basta no cambió); una sola repetición de Milei no dice con qué frecuencia el juicio solo con la web da `contradicha`.

### 9.3 Desglose del tiempo del camino actual (15 nov 2026)

Con autorización del usuario. Camino actual (regla de suficiencia nueva y opción A) frente a solo la web, con el LLM, Google y Tavily reales: **Milei 3 veces; inflación de Colombia y Keiko Fujimori una vez cada una** (las dos que en la sección 9 no encontraron nada en la fuente previa), y las mismas cinco afirmaciones solo con la web. Son 10 ejecuciones de `verify_claim`; en Milei se alternó cuál modo iba primero. El tiempo de cada fase se midió envolviendo el LLM, las búsquedas y el descargador: **consultas** (las dos llamadas al LLM que escriben la consulta de la web y la corta), **búsquedas** (las llamadas a Google y a Tavily), **descargas** (todas las páginas bajadas) y **juicio** (las llamadas al juez). Lo que falta para el total (selección de pasajes y demás) fue de 0,00 a 0,03 s.

**Créditos de Tavily gastados: 10** (5 con la fuente previa y 5 solo con la web: una búsqueda por afirmación en cada ejecución). En estas cinco afirmaciones la fuente previa **no bastó en ninguna**, por lo que **no ahorró ningún crédito**. El punto de uso de Tavily marcó 136 antes y después, otra vez sin confirmar.

Medias por afirmación, en segundos (entre paréntesis, cuántas llamadas o páginas):

| Afirmación y camino | Total | Consultas LLM (web + corta) | Búsquedas (Google + Tavily) | Descargas (previa + web) | Juicio | Créditos |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Milei** con previa (3 ejecuciones) | **10,7** | 1,45 + 0,38 = 1,8 | 0,68 + 0,25 = 0,9 | 0,65 (2) + 4,79 (3) = 5,4 | 2,5 (2 juicios) | 1 |
| Milei solo web (3) | 6,6 | 1,34 | 0,54 | 3,5 (3) | 1,2 (1 juicio) | 1 |
| **Inflación** con previa (1) | **7,9** | 1,10 + 0,60 = 1,7 | 0,47 + 1,40 = 1,9 | 0 + 3,23 (4) = 3,2 | 1,1 (1) | 1 |
| Inflación solo web (1) | 4,8 | 1,07 | 0,41 | 2,3 (4) | 1,1 (1) | 1 |
| **Keiko** con previa (1) | **7,9** | 1,35 + 0,74 = 2,1 | 0,45 + 1,47 = 1,9 | 0 + 2,72 (3) = 2,7 | 1,2 (1) | 1 |
| Keiko solo web (1) | 3,6 | 1,37 | 0,34 | 0,9 (3) | 1,0 (1) | 1 |

Veredictos iguales en los dos caminos: Milei `contradicha` las 6 veces; inflación `fuera_de_contexto`; Keiko `apoyada` (en la sección 9 había salido `insuficiente` porque las páginas no dieron texto útil; ahora se obtuvieron 3, así que el resultado de esa afirmación depende de qué páginas se logran descargar).

**Cuánto de la diferencia es de la fuente previa.** El trabajo de la web es el mismo en los dos caminos (la misma consulta de la web y, a juzgar por el número de páginas descargadas, las mismas páginas), así que lo que varía ahí (Tavily y descargas de la web) es ruido de la red, no de la fuente previa. Lo atribuible a la fuente previa es lo que el solo web no hace:

| Afirmación | Diferencia total | Consulta corta (LLM) | Búsqueda en Google | Descargas de la previa | Juicio de más | **Atribuible a la previa** | Resto: variación de la web |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Milei | +4,1 s | 0,38 | 0,68 | 0,65 | 1,28 | **3,0 s** | +1,1 s |
| Inflación | +3,1 s | 0,60 | 0,47 | 0 | 0 | **1,1 s** | +2,0 s |
| Keiko | +4,3 s | 0,74 | 0,45 | 0 | 0 | **1,2 s** | +3,1 s |

- **Cuando no encuentra nada** (inflación, Keiko): la fuente previa añade unos **1,1 a 1,2 s** (la consulta corta y la llamada a Google), tal como se había estimado. Lo demás de la diferencia medida, de 2,0 a 3,1 s, es variación de Tavily y de las descargas con consultas y páginas idénticas (en inflación y Keiko la ejecución con previa iba siempre primera, así que no se puede separar la variación de un efecto de orden con una sola pasada).
- **Cuando encuentra algo que no basta** (Milei): añade unos **3,0 s**, el **doble** que cuando no encuentra nada: la consulta corta y Google (1,1 s), 2 páginas descargadas de más (0,65 s) y **un juicio de más (1,3 s)**. Es el camino más caro y el único donde se pagan las páginas y el juicio descartados por la opción A.
- Las llamadas al juez duran de 1,0 a 1,3 s cada una; las descargas son la fase más larga (de 0,9 a 4,8 s de media) y la más variable.

**Qué dice esto.** La fuente previa solo compensa cuando basta (sección 9: ahorra 1 crédito y alrededor de 0,6 s). En las otras dos situaciones **cuesta de 1,1 a 3,0 s por afirmación sin ahorrar créditos**. Con esta muestra pequeña (5 afirmaciones, una sola ejecución para inflación y Keiko) los números son orientativos, y de cuántas afirmaciones reales tienen verificación publicada depende que compense o no.

## 10. Lo que no se verificó

- **Muestra pequeña:** el recorrido de la sección 9 son 5 afirmaciones y un caso, con 2 rondas; no hay intervalos y la variación entre ejecuciones es del tamaño del efecto en el tiempo. Los créditos de Tavily salen del conteo del guion, sin confirmación del punto de uso de Tavily. Tampoco se comprobaron los cupos de la API de Google.
- **Ninguna medición de calidad**: ni del prompt `v2`, ni de 3 afirmaciones frente a 5, ni de 1 consulta frente a 2, ni de cuánto resuelve la fuente previa (con 3 afirmaciones de prueba, 2 tuvieron resultados). La evidencia congelada del piloto ya no sirve para repetir esos casos (las consultas cambian).
- **Riesgo conocido:** una verificación previa de **otro** hecho parecido («el puente de 2020» frente a «el de 2024») puede llegar al juez. Lo contienen la guarda de nombres y cifras y la cita literal, pero no se eliminó: hay que medirlo.

## 11. Pendiente

1. **Decidir si el coste de la fuente previa compensa** (sección 9.3): cuando no basta cuesta de 1,1 a 3,0 s por afirmación sin ahorrar créditos; habría que estimar qué parte del tráfico real tiene una verificación publicada (punto 4 y sección 11.1).
2. Fase 7: comparar `extraccion-v1` y `v2`, y 1 frente a 2 consultas, con el conjunto de ajuste (corridas en vivo, con presupuesto de Tavily por decidir).
3. Medir la fuente previa solo con casos cuya etiqueta no salga de los mismos medios (la tanda `respaldada`).
4. **Medir la fracción de afirmaciones del tráfico real con verificación publicada** (idea en 11.1). **Se deja para cuando haya uso real y se hable con Orlando; no se implementó nada.**

### 11.1 Idea: medir la fracción con tráfico real (no implementada)

**Hoy no se puede medir.** `origen_busqueda` y `consultas_fuente_previa` solo existen en memoria. Lo que se guarda por afirmación es `{id, texto, veredicto, fuente_ids, origen}` y `origen` solo distingue `busqueda` de `base_anterior`; el ejecutor de la Fase 7 tampoco sirve, porque al evaluar se excluyen los verificadores.

**Qué guardar.** Una clave nueva en el JSON de cada afirmación, por ejemplo `fuente_previa: {resultados, origen}` con `origen` en `web`, `verificadores` o `verificadores+web`. Va en el jsonb de `afirmaciones`, **sin migración**; la web ignora las claves que no conoce (`presentation.js` lee solo las suyas y los esquemas no definen la forma de la afirmación). Serían unas 40 líneas más pruebas, en `ClaimResult`, `build_outcome`, `_verify_claim` y `ClaimVerification` (que hoy no guarda cuántos resultados dio la previa).

**Qué contar** (solo afirmaciones con `origen = 'busqueda'` y sin copias, para no contar dos veces lo que viene de la base de D5):

| Medida | Cómo | Qué dice |
| --- | --- | --- |
| Cobertura | % con al menos 1 resultado de la previa | El techo de lo que puede ayudar |
| Suficiencia | % con origen `verificadores` | Los créditos de Tavily ahorrados |
| Suficiencia falsa | revisión a mano de unas 50 con origen `verificadores` | Si la verificación hallada es de la misma afirmación (criterio de la sección 8) |
| Por noticia | % de casos con al menos una afirmación que bastó | Lo que se ve desde la web |

La consulta sería sobre `verificaciones_web` y `jsonb_array_elements(afirmaciones)`, agrupando por `fuente_previa->>'origen'`. **Muestra:** con una fracción cercana al 15 %, unas 200 afirmaciones nuevas dan ±5 puntos al 95 %.

**Qué decide la cifra.** Con los tiempos de la sección 9.3 (+1,1 s cuando no encuentra nada, −0,6 s cuando basta), los segundos de más por cada crédito ahorrado dependen de la fracción `p` que basta (cuenta mía, que ignora el caso «encuentra algo que no basta»):

| `p` | Segundos de más por crédito ahorrado |
| ---: | ---: |
| 10 % | ≈ 9 s |
| 20 % | ≈ 4 s |
| 30 % | ≈ 2 s |
| 54 % (la mezcla medida) | ≈ 0,3 s |

El tiempo extra solo se compensa del todo por encima del 65 %, así que en la práctica el beneficio es el crédito.

**Sesgos a vigilar:** una verificación aparece días después de que el bulo circula, y una noticia analizada hoy puede no tener aún la suya (convendría guardar la fecha del análisis); y la cobertura se concentra en contenido viral o falso, por lo que conviene separar por la clase que predijeron BiLSTM y BETO. **Estimación gratuita antes del tráfico:** lanzar las mismas consultas a la API sobre afirmaciones extraídas de textos de `datasets/`; saldría sesgada hacia arriba, porque lo antiguo está mejor indexado.

5. **Opcional, no se hará por ahora:** `FACTCHECK_ENABLED` para apagarla sin borrar la clave (unas 15 líneas con pruebas; por defecto, «encendida si hay clave»). Basta con vaciar la clave, como se explica en la sección 5.
