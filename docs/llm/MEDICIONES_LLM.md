# Fase 1: mediciones del LLM y elección de la variante

**Fecha:** 15 nov 2026. **Plan:** [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md), Fase 1 (D1, D2 y D8).
**Decisión (D1): se usa `Qwen3-4B-Instruct-2507-Q8_0.gguf`** con `llama-server -c 8192 -np 1`. La eligió el usuario a partir de estos resultados.
**Es una variante de 8 bits** (cuantización Q8_0). [INCREMENTOS.md](../INCREMENTOS.md) sigue diciendo «cuantizado a 4 bits»: está desactualizado y se corregirá más adelante, por indicación del usuario.

## 1. Resumen

| | Q4_K_M | **Q8_0 (elegida)** |
| --- | --- | --- |
| Archivo | 2,50 GB | 4,28 GB |
| VRAM con contexto 8192 | ≈ 4,4–4,5 GB | ≈ 5,9 GB |
| Generación (textos de 320–1.243 palabras) | 66–73 tokens/s | 48,5–50,1 tokens/s |
| Extracción típica (7 textos reales) | 4,2–5,7 s | 4,1–8,3 s |
| Contexto máximo estable (medido) | 32.768 | **16.384** (32.768 con la caché cuantizada, 3.4) |
| Listas de afirmaciones vacías en textos con hechos verificables | **2 de 7**; con otra redacción, 2 de 7 (otros textos) | **0 de 14** (con 20 textos más, ver 3.5) |

La velocidad y la memoria favorecen a Q4_K_M. Se eligió Q8_0 por **fiabilidad**: Q4_K_M devolvió lista vacía en textos que sí contenían hechos comprobables, y si eso ocurre en producción el caso termina como `evidencia_insuficiente` por un fallo del modelo, sin aviso. Con Q8_0 no pasó en ninguna de las 14 corridas.

## 2. Cómo se midió

- **Equipo:** NVIDIA GeForce RTX 5060 Laptop, 8.151 MiB de VRAM, driver 610.74.
- **Servidor:** llama.cpp b12404 (CUDA 13.5), `llama-server -ngl 99 -c <contexto> -np 1 --api-key-file …`, solo en `127.0.0.1`.
- **Cliente:** todas las peticiones pasaron por `backend/services/llm_client.py` (esquema `ClaimExtraction` forzado con `response_format`, `max_tokens` 600, temperatura 0). Los tiempos de prompt y de generación salen del campo `timings` que devuelve el servidor.
- **Textos:** 7 artículos reales en español de `datasets/comun_v1/fragmentos_desarrollo.csv` (conjunto de desarrollo; **no** la prueba congelada), unidos por artículo y elegidos por longitud (≈120, 200, 320, 540, 800, 1.100 y 1.300 palabras; fuentes `v1` y `fakedes`, reales y falsos). Identificadores en el anexo A. Los textos no se copian a este repositorio.
- **Instrucciones usadas:** una redacción provisional, la misma en las dos variantes (anexo B). **No es el prompt definitivo**: la versión que se guarda como `version_prompts` es de la Fase 3.
- **Contexto máximo estable:** el mayor contexto en que el servidor carga y responde sin error, dentro de 300 s, una petición cuyo prompt llena casi todo el contexto (contexto menos ≈1.000 tokens). Se midió también la VRAM libre en el pico.
- Cada texto se probó **una vez** por variante, tras una petición de calentamiento que no se cuenta.

## 3. Resultados

### 3.1. Extracción de afirmaciones (contexto 8192)

| Palabras | Q4_K_M | Q8_0 |
| --- | --- | --- |
| 120 | **0 afirmaciones**, 0,44 s | 5, 4,1 s |
| 199 | **0 afirmaciones**, 0,43 s | 5, 6,3 s |
| 320 | 5, 5,7 s | 5, 6,2 s |
| 545 | 5, 4,2 s | 5, 5,8 s |
| 801 | 5, 4,8 s | 5, 6,1 s |
| 1.079 | 5, 4,4 s | 5, 6,6 s |
| 1.243 | 5, 5,5 s | 5, 8,3 s |

- **Tokens por palabra:** unos 1,6 en estos textos (el artículo de 1.243 palabras fueron 2.094 tokens de prompt con las instrucciones).
- **Salida:** 209–371 tokens con 5 afirmaciones. Con `max_tokens` 600 ninguna respuesta se cortó.
- **Velocidad del prompt:** 2.000–3.300 tokens/s en las dos variantes (sin contar el texto de 120 palabras, demasiado corto para medirla: 17–19 tokens/s).
- **JSON válido:** todas las respuestas recibidas, en ambas variantes, cumplieron `ClaimExtraction` (las únicas fallas fueron los tiempos agotados de Q8_0 en contexto 24.576 y 32.768).

### 3.2. Memoria y contexto (VRAM de la GPU, en MiB; total 8.151)

| Contexto | Q4_K_M: pico / libre / tiempo | Q8_0: pico / libre / tiempo |
| --- | --- | --- |
| 8.192 | 4.407 / 3.744 / 8,0 s | 5.925 / 2.226 / 10,8 s |
| 16.384 | 5.553 / 2.598 / 13,2 s | 7.083 / 1.068 / 17,7 s |
| 24.576 | 6.742 / 1.409 / 21,5 s | **falló: sin respuesta en 300 s** (pico 7.662, libre 489) |
| 32.768 | 7.713 / 438 / 34,1 s | **falló: sin respuesta en 300 s** (pico 7.654, libre 497) |

- Con Q8_0, a partir de 24.576 la memoria queda al límite y no responde en 300 s. La causa y el arreglo están en 3.4.
- Antes de lanzar el servidor, otros programas ya usaban entre 495 y 797 MiB de la GPU (variaba entre corridas).

### 3.3. Comprobación con otra redacción de las instrucciones

Para saber si el fallo de Q4_K_M dependía del texto de las instrucciones, se repitió con una variante B (anexo B), mismos 7 textos:

| | Q4_K_M | Q8_0 |
| --- | --- | --- |
| Instrucciones A | vacía en 120 y 199 palabras | ninguna vacía |
| Instrucciones B | vacía en 120 y **1.079** palabras | ninguna vacía |

Q4_K_M sigue fallando en 2 de 7, pero **en textos distintos**: su comportamiento es inestable, no un efecto de una frase concreta.

### 3.4. Atasco de Q8_0 con contexto grande: causa y arreglo

**Causa:** falta de VRAM. Con la caché de contexto en 16 bits (lo normal), los pesos de Q8_0 más la caché de 24.576 tokens llenan la GPU (7,7 GB de 8,1 GB) y Windows empieza a usar memoria compartida del sistema. Entonces todo se vuelve lento, incluso con un prompt corto; con un prompt lleno no terminaba en 300 s. No es un problema del largo del texto.

**Arreglo:** cuantizar la caché de contexto a 8 bits y activar la atención flash, con `-ctk q8_0 -ctv q8_0 -fa on`. Una petición por configuración, Q8_0, un solo caso:

| Configuración | Contexto | Prompt | VRAM dedicada (pico) | Memoria compartida | Tiempo | Prompt | Generación |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Normal | 8.192 | 992 tok | 6.045 MiB | 562 MiB | 5,7 s | 3.268 tok/s | 50,1 tok/s |
| Normal | 24.576 | 992 tok | 7.710 MiB | **562 → 725 MiB** | 12,1 s | **506 tok/s** | 27,0 tok/s |
| Caché q8_0 + atención flash | 24.576 | 992 tok | 6.725 MiB | 562 MiB | 5,9 s | 3.101 tok/s | 48,6 tok/s |
| Caché q8_0 + atención flash | 24.576 | 23.166 tok | 6.711 MiB | 562 MiB | 25,1 s | 1.737 tok/s | 27,1 tok/s |
| Caché q8_0 + atención flash | 32.768 | 31.164 tok | 7.361 MiB | 562 MiB | 38,1 s | 1.321 tok/s | 23,4 tok/s |

- Con la caché cuantizada no se usa la memoria compartida, la velocidad de un prompt corto vuelve a ser la normal y el contexto de 32.768 funciona.
- **No se midió si esa cuantización afecta la calidad de las afirmaciones.** Por eso la propuesta sigue siendo `-c 8192` con la caché normal, que alcanza para la extracción. Estas opciones quedan solo por si algún día hace falta más contexto, y habría que evaluarlas antes.
- Es una prueba puntual (una petición por fila), no una medición repetida.

### 3.5. Datos inventados: instrucciones y validador

**Problema:** el LLM completa de memoria cifras que el texto no trae (por ejemplo «70 por ciento» o «categoría 4»), añade nombres (por ejemplo «España» o «Estadio Azteca») y, con las instrucciones iniciales, devuelve lista vacía sobre todo en noticias falsas.

**Qué se probó** (Q8_0, `-c 8192`, esquema del plan, 20 textos reales: los 7 de arriba más 13; 7 son falsos). «Cifra ausente» y «nombre ausente» cuentan afirmaciones que contienen una cifra o un nombre propio que no aparece en el texto:

| Instrucciones | Listas vacías | Afirmaciones | Cifra ausente | Nombre ausente |
| --- | --- | --- | --- | --- |
| A (iniciales, anexo B) | 4 | 80 | 5 | 6 |
| C (reglas numeradas y estrictas) | **11** | 44 | 0 | 1 |
| D (A + «usa solo lo que dice el texto» + «casi toda noticia tiene hechos») | 6 | 70 | 1 | 0 |
| E (D + respetar quién dice cada cosa) | 6 | 70 | 0 | 2 |
| F (D + extraer también lo falso o dudoso) | 3 | 83 | 1 | 2 |
| G (E + extraer también lo falso o dudoso) | 5 | 75 | 0 | 4 |
| **H (rol de verificador de datos)** | 2 | 89 | 0 | 1 |

Las reglas estrictas (C) eliminan lo inventado, pero el modelo se refugia en la lista vacía en más de la mitad de los textos. **Se adoptó H** (`extraccion-v1`, [prompts.py](../../backend/services/verification/prompts.py)).

**Confirmación con 20 textos nuevos** (10 reales y 10 falsos, no usados para elegir): A: 3 listas vacías (2 en falsos), 79 afirmaciones, 0 cifras ausentes, 3 nombres ausentes. H: 3 vacías (2 en falsos), 80 afirmaciones, 0 cifras ausentes, 1 nombre ausente. **La ventaja de H en listas vacías no se confirmó**; la de nombres ausentes sí, pero con números pequeños.

**Validador determinista:** [claims.py](../../backend/services/verification/claims.py) comprueba que cada cifra y cada nombre propio (con mayúscula inicial, salvo la primera palabra) de una afirmación aparezca en el texto, sin distinguir tildes ni mayúsculas ni separadores de miles, y descarta las que no. `extract_claims` junta las instrucciones, la llamada al LLM y esa comprobación, y devuelve las afirmaciones aceptadas (numeradas de nuevo) y las rechazadas con su motivo. Pruebas: `backend/tests/test_claims.py` (15).

**Resultado con el código del repositorio** y Q8_0 real, en los 40 textos: **172 afirmaciones aceptadas y 2 rechazadas** (ambas por nombre: «Colombia», deducido de «Barranquilla», y «Entertainment» en «World Wrestling Entertainment»); 4 textos con lista vacía del modelo (10 %), 2 de ellos falsos. Ninguna cifra inventada llegó a pasar, aunque con las instrucciones H el modelo ya casi no las producía (0 de 169 afirmaciones frente a 5 de 159 con A en los mismos 40 textos), así que el validador no tuvo mucho que filtrar.

**Lo que no se arregló:**
- **Atribución.** El modelo cuenta como hecho lo que el texto presenta como denuncia, o cambia quién actúa. En el texto de 199 palabras, **ninguna** de las variantes D a H dejó de escribir que los habitantes declaran haber comprado las credenciales, cuando el texto dice que otros declaran que las están comprando. Las dos con regla de atribución (E y G) sí escribieron «fue descubierta comprando» en vez de afirmarlo como un hecho, pero no mejoraron el resto. Se medirá con el conjunto de la Fase 7.
- **Lista vacía en noticias falsas.** Sigue habiendo textos falsos con afirmaciones concretas que devuelven lista vacía (en la muestra nueva, 2 de 10). Forzar al menos una afirmación lo evitaría, pero se aparta del esquema del plan, que permite la lista vacía; no se hizo.
- **Falsos positivos del validador.** Descarta una afirmación acertada si la cifra del texto está escrita con letras («doce») o si el nombre es una deducción correcta.
- **Cifras que borra el conjunto de pruebas.** Varios textos del conjunto traen cifras en blanco («lanzada el de marzo del año»); en páginas reales esas cifras aparecen, así que estas mediciones exageran cuánto inventa el modelo.

## 4. Límites reales para el plan

| Parámetro | Valor medido | Propuesta (a confirmar en las fases siguientes) |
| --- | --- | --- |
| Contexto del servidor | Q8_0 estable hasta 16.384 con la caché normal; hasta 32.768 con `-ctk q8_0 -ctv q8_0 -fa on` (3.4; calidad no medida) | `-c 8192`. Un prompt de 7.356 tokens (más de lo que pesa el tope de 20.000 caracteres, que se estima en unos 6.000) se resolvió en 10,8 s |
| Salida de la extracción | 209–371 tokens | `max_tokens` 600 |
| `LLM_TIMEOUT` | Petición más lenta con Q8_0: 17,7 s (prompt de 15.550 tokens) | Dejar el valor por defecto de 120 s |
| Duración de una extracción | 4,1–8,3 s con Q8_0 | — |
| Capacidad del trabajador | — | **Estimación, no medida:** un caso con 5 afirmaciones puede necesitar unas 11 llamadas al LLM (1 de extracción más consulta y juicio por afirmación) de ≈5 s cada una, es decir, del orden de 1 minuto de LLM por caso, sin contar búsqueda ni descargas. Se medirá en las fases 4 y 5 |

## 5. Hallazgos para las fases siguientes

1. **Listas vacías en silencio.** Fue la razón de elegir Q8_0 frente a Q4_K_M. Con Q8_0 y las instrucciones `extraccion-v1` siguen apareciendo (4 de 40 textos, la mitad en noticias falsas; ver 3.5). La Fase 3 debe distinguir «el modelo no encontró nada» (`rechazadas` vacío) de «todo lo que encontró se descartó» (`rechazadas` con elementos): el plan convierte lo primero en `evidencia_insuficiente` (sección 4.5, Paso 1).
2. **Cifras y nombres inventados.** Resuelto en gran parte con las instrucciones `extraccion-v1` y el validador (3.5). Los textos del conjunto traen cifras borradas, así que los números de antes exageran el problema real.
3. **Errores de fidelidad que no detecta el validador.** Atribuciones cambiadas (3.5) y monedas: en el texto de 1.079 palabras con las instrucciones iniciales Q8_0 escribió «250 dólares» donde el texto dice «250 euros», y Q4_K_M cambió «$18» por «18 euros». Con `extraccion-v1` el caso de la moneda no se repitió, pero tampoco hay una comprobación que lo impida. Hay que medirlo con el conjunto de la Fase 7.
4. **Añadidos de contexto.** Las dos variantes escribían «Gobierno de España», aunque el texto no contiene la palabra «España» (se deduce de que menciona a su presidente, Pedro Sánchez). El validador de nombres lo descarta.
5. **Comprobaciones automáticas.** Señalan dónde leer (cifras y nombres ausentes del texto, dependencia del texto); no sustituyen la lectura manual de las afirmaciones.

## 6. El cliente

- `backend/services/llm_client.py`: `LlmClient.complete_json(mensajes, ClaimExtraction)`; el esquema se envía como `response_format` y la respuesta se valida con pydantic.
- Dos fallas distintas: `LlmUnavailable` (no conecta, tiempo agotado, clave rechazada u otro error HTTP) y `LlmInvalidResponse` (vacía, cortada por `max_tokens` o fuera del esquema). Cada una trae un `code`: `llm_no_disponible`, `tiempo_agotado`, `no_autorizado` o `salida_invalida`.
- Se reintentan solo conexión caída y estados 408, 425, 429 y 5xx (2 reintentos con espera creciente). No se reintentan el tiempo agotado, la clave rechazada, otros 4xx ni las respuestas inválidas: eso lo reintenta la cola (3 intentos, D11).
- Configuración: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT` y `LLM_API_KEY` ([backend/.env.example](../../backend/.env.example), sin valores). La clave real está en `backend/.env.desarrollo` y en `backend/.local/llm/api-key.txt` (ambos fuera de Git); a `llama-server` se le pasa con `--api-key-file`, así no aparece en la línea de comandos.
- El cuerpo de la petición va en UTF-8 explícito.
- Pruebas: `backend/tests/test_llm_client.py`, 19 pruebas con un servidor simulado y otro HTTP local (`unittest`, sin llama-server).
- `backend/services/verification/claims.py` (`extract_claims`) usa el cliente para el paso 1 del plan y valida el resultado; sus instrucciones versionadas están en `prompts.py` (`extraccion-v1`). Ver 3.5.

## 7. D8: llamada con clave

- **Comprobado en `127.0.0.1`:** el cliente, configurado desde las variables de `backend/.env.desarrollo`, obtuvo 5 afirmaciones con JSON válido de un artículo real de 545 palabras. Con clave equivocada y sin clave, el servidor respondió 401 y el cliente lanzó `LlmUnavailable` con `code="no_autorizado"`.
- **Sin comprobar:** la llamada desde otro equipo o por la IP de red local. Se decidió no abrir el servidor a la red durante la prueba. **Queda por cerrar cómo se conectan los dos equipos** (red local u otra) y si hace falta una regla de firewall.
- `/health` de `llama-server` responde sin clave aunque se use `--api-key-file`; solo `/v1/…` la exige.

## 8. Limitaciones de estas mediciones

- 7 textos y una sola corrida por texto y variante: son mediciones puntuales, no estadísticas.
- La comparación de calidad se hizo leyendo las afirmaciones contra el texto; es mi lectura, no una evaluación con etiquetas (esa es la Fase 7).
- Los textos de prueba son noticias reales con ruido propio del conjunto (cifras borradas), distintas de los textos que enviaría la extensión.
- La VRAM «libre» depende de lo que tengan abierto otros programas en el equipo en ese momento.

## Anexo A. Textos usados (identificadores de `id_articulo`)

| Palabras | Fuente | Clase | `id_articulo` |
| --- | --- | --- | --- |
| 120 | fakedes | real | `9ae219617e94e9551e162c02b9f4c257547a1fc09566a606f049ac6af071f9a8` |
| 199 | v1 | falsa | `d9d81baf7c7e1010a27f50c6a009f40a9285a661e29cb8a33806d03d6539351b` |
| 320 | v1 | real | `a0132459921d07c8ae1e0ddc1e5590b4804b2a6fcde60597ff4791136ec2f3f7` |
| 545 | fakedes | falsa | `9ad7cc35d81ce6b966801ecfed2f31b753b76226afb88db993ba72b380dadbd5` |
| 801 | fakedes | real | `9d53f5d8edc6e6d7aa8ee9de57b804465906e9bd8200cc86f2f966cea22b9f95` |
| 1.079 | fakedes | falsa | `a62f4da954a9f0652387c317a13f20a17aab4a2fb551b9aaf02f10cf3d22ec8c` |
| 1.243 | v1 | real | `f3d07532fbdec0fcf4fb351390b698a1125bc04efcc511424d781beaf16885d4` |

## Anexo B. Instrucciones provisionales

**A (sistema):** «Eres un asistente que extrae afirmaciones verificables de una noticia. Devuelve como máximo 5 afirmaciones sobre hechos concretos (cifras, fechas, lugares, atribuciones a personas o instituciones, eventos) que se puedan comprobar con fuentes externas. Reescribe cada afirmación para que se entienda sola: sin pronombres ni referencias al texto («el texto», «esta noticia») y con los nombres completos. Descarta opiniones, predicciones y juicios de valor. No inventes datos que no estén en el texto. Si no hay ninguna afirmación verificable, devuelve una lista vacía. Numera con id desde 1.» El mensaje del usuario es el texto de la noticia.

**Estas dos redacciones (A y B) fueron las de las mediciones 3.1 a 3.3. La adoptada (`extraccion-v1`) está en `backend/services/verification/prompts.py` y se comparó en 3.5.**

**B:** lo anterior, más: «Casi toda noticia contiene al menos un hecho comprobable, aunque el texto sea corto: devuelve lista vacía solo si el texto es pura opinión y no menciona ningún hecho.» El mensaje del usuario es «Noticia:» seguido del texto.

**Esquema forzado:** `{"afirmaciones": [{"id": 1–5, "texto": 10–500 caracteres}, …]}`, con 5 elementos como máximo ([backend/schemas/verification.py](../../backend/schemas/verification.py)).
