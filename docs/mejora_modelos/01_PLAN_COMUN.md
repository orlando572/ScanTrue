# Plan de mejora común: datos, evaluación y calibración

**Fecha:** 7 de noviembre de 2026
**Se aplica a:** BiLSTM y mBERT por igual.
**Responsable:** Orlando construye el conjunto común y el evaluador. El responsable de mBERT los recibe y no los modifica.

Documento anterior: [00_ANALISIS_DATASETS.md](00_ANALISIS_DATASETS.md). Planes por modelo: [02_PLAN_BILSTM.md](02_PLAN_BILSTM.md) y [03_PLAN_MBERT.md](03_PLAN_MBERT.md).

## 1. Por qué hace falta un plan común

- Los dos modelos entrenaron con **casi los mismos datos** (los CSV del BiLSTM; mBERT quitó 278 filas) y llegaron al **mismo F1 externo** (0,603 y 0,600). El límite está en los datos y la evaluación, no en la arquitectura.
- La validación actual (132–170 filas, mismas fuentes que el entrenamiento) **no predice** el resultado externo: 0,765 → 0,603 en el BiLSTM y 0,939 → 0,600 en mBERT.
- La prueba externa de 606 premia la longitud: un clasificador que solo cuenta palabras saca 0,663.
- Las probabilidades no están calibradas: en el nivel «Muy probablemente falso» de la extensión, solo el 60 % de los textos son falsos.
- Cada modelo usa su propia convención de etiquetas y su propia versión de los datos, así que **no se pueden comparar ni combinar con rigor**.

## 2. Reglas que no cambian durante todo el plan

1. **Un solo conjunto común,** con un único manifiesto de hashes. Ningún modelo usa otra versión de los datos.
2. **Una sola convención de etiquetas: `etiqueta_falsa` = 1 si es falsa y 0 si es real.** Coincide con mBERT (`0=REAL, 1=FALSA`) y con `probabilidad_falsa` del backend. El BiLSTM es el que se adapta (ver [02_PLAN_BILSTM.md](02_PLAN_BILSTM.md)).
3. **La prueba congelada no se abre** hasta el paso final. Nadie mira sus resultados para elegir nada.
4. **Toda decisión se toma con la validación por fuente** (sección 4) y con las reglas de la sección 6, fijadas antes de entrenar.
5. **Cada corrida guarda probabilidades por ID,** no solo la clase predicha. Sin probabilidades no hay calibración ni combinación.

## 3. Construcción del conjunto común (`comun_v1`)

### 3.1. Fuentes

| Fuente | Entra | Filtro |
| --- | --- | --- |
| Spanish Fake News Corpus v1 | Sí | Sin dominios de sátira |
| FakeDeS | Sí | Sin dominios de sátira ni redes sociales |
| PolyglotFakeFacts (español) | Sí | Peso limitado (sección 3.4) |
| FalleDesinfo_ES | Solo prueba congelada | — |
| Sátira de v1, fuente política, USMSC/Edds residual | Solo en brazos de ablación (sección 3.6) | — |
| Acosta, Zenodo, X-FACT, FakeCovid, FactOReS, RUN-AS, FLARES | No | — |

**Dominios de sátira:** `eldizque.com`, `elruinaversal.com`, `haynoticia.es`, `lavozpopular.com`, `elmundotoday.com` (la lista que ya usa la política v4 de mBERT).
**Redes sociales:** `facebook.com`, `m.facebook.com`, `twitter.com`, `x.com`, `whatsapp.com`.

**Decisión (Orlando, 7 de noviembre de 2026):** la sátira queda **fuera del conjunto principal**, porque no es desinformación y hoy infla la validación. Su efecto se mide solo en el brazo de ablación `+satira`.

**Versión 1.1 (Orlando, 7 de noviembre de 2026):** se quitan los artículos que no están en español. PolyglotFakeFacts declara todo como español, pero trae algunas falsas en inglés, francés o italiano: 8 artículos, todos falsos de Polyglot (7 del desarrollo y 1 de la prueba congelada). Se detectan con palabras funcionales exclusivas de cada idioma (`idioma_probable` en `datos_comunes/limpieza.py`) y se quitan **después** de elegir la prueba congelada, así que el resto de la partición no cambia. Además, las falsas de Polyglot vienen de medios rusos, bielorrusos o moldavos y probablemente son traducciones, mientras que sus reales son de El Mundo: es otro motivo para leer el pliegue F3 con cautela.

### 3.2. Normalización y limpieza de marcas de procedencia

Aplicada **igual para los dos modelos**, antes de fragmentar:

- Unicode NFC, entidades HTML decodificadas y espacios unificados. Se conservan mayúsculas, tildes y puntuación: mBERT y BETO son *cased*, y el BiLSTM ya pasa a minúsculas en su propio tokenizador.
- **Quitar marcas que identifican al medio,** con una lista de patrones revisada a mano:
  - Datelines al inicio («Ciudad (Agencia) –», «MADRID, 12 Ene. (EUROPA PRESS) –»).
  - Firmas y créditos («Por Fulano», «Foto: …», «Redacción …»).
  - URLs, menciones `@`, hashtags de cierre y textos fijos de pie («Síguenos en…», «Lee también…», «Comparte esta noticia»).
- **Registrar** en el manifiesto cuántas filas cambió cada patrón, con 20 ejemplos de antes y después por patrón para revisión.

### 3.3. Grupos para evitar fugas

- Se reutilizan los grupos del unificado: misma huella de texto, titular específico, cuerpo o URL.
- Se añade la detección de casi duplicados por fragmentos de 5 palabras que encontró 38 pares en la auditoría de mBERT.
- **Todos los fragmentos de un artículo comparten grupo,** y un grupo nunca se reparte entre particiones.

### 3.4. Fragmentos con el tamaño que envía la extensión

La extensión envía la selección del usuario, con un mínimo de 100 tokens. El conjunto se arma con eso:

- **Unidad de trabajo:** el fragmento, no el artículo.
- **Tamaño variable entre 100 y 400 tokens** del tokenizador del BiLSTM (`bilstm/modelo.py:tokenize`), cortado en límite de oración. Para cada fragmento se sortea un tamaño objetivo **sin mirar la clase**; si el artículo es más corto, se toma completo. Se usa ese tokenizador para que el mínimo coincida con el del backend.
  - Variable porque la extensión envía lo que el usuario seleccione: a veces un párrafo, a veces casi todo el artículo.
  - Hasta 400 porque así cada modelo puede probar si le sirve leer más (BiLSTM 192 frente a 320; mBERT 256 frente a 512) con los mismos datos. Ver [02_PLAN_BILSTM.md](02_PLAN_BILSTM.md) y [03_PLAN_MBERT.md](03_PLAN_MBERT.md).
  - **Si el uso real ya está registrado,** sustituir el sorteo uniforme por la distribución real de longitudes: el historial de análisis guarda `tokens_leidos` por modelo, aunque ese valor ya viene recortado (192 en el BiLSTM y 512 en mBERT).
  - Como las falsas son más cortas, sus fragmentos largos serán más escasos. La referencia de solo longitud (sección 4.4) comprueba que eso no reintroduce el atajo; si lo hace, se baja el tope de 400.
- **Titular:** solo en el primer fragmento de cada artículo, al inicio, como lo pondría un usuario que selecciona desde el título.
- **Máximo 4 fragmentos por artículo,** tomados de forma uniforme a lo largo del texto. Así un artículo largo no pesa por diez.
- **Artículos con menos de 100 tokens** (92 casos) se descartan, porque la extensión tampoco los aceptaría.
- **Peso por artículo:** cada fragmento lleva `peso = 1 / n_fragmentos_del_artículo`. Así cada artículo cuenta lo mismo, y las reales, más largas, no se multiplican por su longitud.
- **Peso por fuente:** Polyglot entra con un peso total no mayor al de cada otra fuente, porque sus clases se separan por medio al 100 %.

Resultado estimado: entre **4.000 y 5.000 fragmentos** de 1.868 artículos, con unas 2 reales por cada falsa. El número exacto depende del sorteo de tamaños y se registra en el manifiesto.

**Efecto buscado:** con el tamaño de fragmento decidido sin mirar la clase, la longitud deja de indicar la clase en el entrenamiento y en la evaluación.

### 3.5. Particiones

| Partición | Contenido | Uso |
| --- | --- | --- |
| **Prueba congelada** | 15 % de los grupos de v1, FakeDeS y Polyglot, estratificado por fuente y clase, más los 33 de FalleDesinfo | Solo al final, una vez |
| **Desarrollo** | El 85 % restante | Validación cruzada por fuente (sección 4) |

La prueba congelada no es inédita para las personas (FakeDeS ya se miró antes), pero sí lo es **para toda decisión a partir de ahora**. Es lo mejor que se puede hacer sin datos nuevos.

### 3.6. Brazos de ablación

Se generan como archivos aparte, **solo con filas de entrenamiento** (nunca entran en validación ni en la prueba congelada):

| Brazo | Qué añade | Para responder |
| --- | --- | --- |
| `+satira` | Sátira de v1 como falsa | ¿Ayuda o confunde a detectar desinformación? |
| `+usmsc` | USMSC/Edds residual | ¿Los fragmentos sin procedencia aportan algo medido por fuente? |
| `+politica` | Hasta 1.000 parejas real/falsa de la fuente política, cada pareja en un mismo grupo | ¿Las parejas sintéticas enseñan algo transferible? |

### 3.7. Archivos que se entregan

Carpeta `datasets/comun_v1/` (ignorada por Git):

| Archivo | Contenido |
| --- | --- |
| `fragmentos_desarrollo.csv` | Un fragmento por fila (columnas abajo) |
| `fragmentos_prueba_congelada.csv` | Igual, solo para el paso final |
| `ablacion_satira.csv`, `ablacion_usmsc.csv`, `ablacion_politica.csv` | Filas extra de entrenamiento |
| `pliegues.json` | Qué fuentes forman cada pliegue de validación |
| `manifest.json` | SHA-256 de cada archivo, conteos por fuente/clase/pliegue, versión del script, listas de dominios y patrones |
| `REPORTE.md` | Conteos, ejemplos de limpieza y avisos |

Columnas de los CSV de fragmentos:

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `id_fragmento` | texto | `<id_articulo>#<n>` |
| `id_articulo` | texto | ID del unificado |
| `grupo` | texto | Grupo de duplicados |
| `fuente` | texto | `v1`, `fakedes`, `polyglot`, `falledesinfo` |
| `dominio` | texto | Dominio de la URL, si existe (auditoría, nunca entrada del modelo) |
| `texto` | texto | Fragmento limpio, **única entrada del modelo** |
| `etiqueta_falsa` | 0/1 | 1 = falsa |
| `peso` | real | Peso por artículo y fuente |
| `tokens_bilstm` | entero | Tokens según el tokenizador del BiLSTM |
| `pliegue` | texto | Fuente que queda fuera en cada pliegue (sección 4) |

## 4. Protocolo de evaluación

### 4.1. Validación cruzada dejando una fuente fuera (selección)

Tres pliegues: se entrena con dos fuentes y se valida en la tercera.

| Pliegue | Entrena con | Valida en |
| --- | --- | --- |
| F1 | FakeDeS + Polyglot | v1 |
| F2 | v1 + Polyglot | FakeDeS |
| F3 | v1 + FakeDeS | Polyglot |

- **Métrica de selección:** media de **F1 macro a nivel de artículo** de los tres pliegues. La probabilidad del artículo es la media de las de sus fragmentos.
- **El pliegue F3 se informa, pero no decide solo:** Polyglot se separa por medio al 100 %, así que un buen resultado ahí puede ser solo reconocer a El Mundo.
- Dentro de cada pliegue se separa un 10 % de los grupos de entrenamiento para elegir la época (parada temprana). Nunca se usa la fuente que quedó fuera para eso.
- **Semillas:** 3 por configuración (42, 43, 44). Se informa media y desviación.

### 4.2. Predicciones fuera de pliegue

Cada corrida guarda la probabilidad de cada fragmento de la fuente que quedó fuera. Juntando los tres pliegues se obtiene **una predicción por fragmento, hecha por un modelo que no vio esa fuente**. Con eso se hace:

- La calibración (sección 5).
- El ajuste de pesos para combinar los dos modelos.
- La tabla de niveles de la extensión (sección 5.3).
- La comparación entre modelos con bootstrap pareado por artículo.

### 4.3. Métricas obligatorias

Para cada configuración, a nivel de fragmento y de artículo, global y por fuente:

- F1 macro, F1 de falsa, precisión y recall de falsa.
- Tasa de falsas alarmas: reales marcadas falsas / total de reales.
- AUC-ROC y AP (precisión media).
- Brier y ECE (error de calibración esperado, 10 tramos).
- Matriz de confusión en orden `[real, falsa]`.
- Intervalo de confianza del 95 % para F1 macro por bootstrap de artículos (1.000 remuestreos).

### 4.4. Referencias obligatorias

Toda configuración debe compararse con estas dos referencias, evaluadas con el mismo protocolo:

1. **Solo longitud:** regresión logística sobre el número de tokens. Con el tamaño de fragmento sorteado sin mirar la clase, debería quedar cerca de 0,5. Si no, la fragmentación no quitó el atajo y hay que bajar el tope de 400 tokens.
2. **TF-IDF de caracteres 3–5 + regresión logística,** con los mismos pesos. Un modelo neuronal que no lo supere no justifica su costo.

## 5. Calibración, umbral y combinación

### 5.1. Calibración por modelo

- **Método:** escalado de temperatura. Un único parámetro `T` que divide los logits; no cambia qué texto se considera más falso que otro, solo cuánto se confía.
- **Ajuste:** con las predicciones fuera de pliegue (sección 4.2), minimizando el log-loss.
- **Se guarda** `T` en el contrato de inferencia de cada modelo (ver planes por modelo).

### 5.2. Umbral y combinación

- **Combinación:** regresión logística sobre los logits calibrados de los dos modelos, ajustada con las predicciones fuera de pliegue. Reemplaza los pesos fijos 70/30 de `backend/core/config.py`. Si un modelo no aporta, su coeficiente sale cercano a 0 y eso también es un resultado.
- **Umbral de clase:** se mantiene en 0,5 sobre la probabilidad calibrada, salvo que Orlando fije un costo distinto para falsas alarmas y falsas omisiones.
- **Regla de discrepancia:** si un modelo da más de 0,5 y el otro menos, y la diferencia supera 0,4, el backend devuelve un valor dentro de la franja «incierto». El umbral de 0,4 se revisa con las predicciones fuera de pliegue.

### 5.3. Comprobación de los niveles de la extensión

Con las predicciones fuera de pliegue ya calibradas y combinadas, se rellena esta tabla. Es la prueba de que los porcentajes que ve el usuario dicen la verdad:

| Nivel en la extensión | Fragmentos | % realmente falsas | Objetivo |
| --- | ---: | ---: | --- |
| 0–20 «Muy probablemente verdadero» | | | ≤ 20 % |
| 20–40 «Probablemente verdadero» | | | 20–40 % |
| 40–60 «Resultado incierto» | | | 40–60 % |
| 60–80 «Probablemente falso» | | | 60–80 % |
| 80–100 «Muy probablemente falso» | | | ≥ 80 % |

Si un nivel queda vacío o fuera de su rango, se informa así. No se fuerza: con estos datos puede que el modelo nunca llegue a 80 % de forma honesta, y eso es mejor que mostrar un 95 % que solo acierta el 60 % de las veces.

## 6. Reglas de decisión fijadas antes de entrenar

- **Un cambio se adopta** si sube la media de F1 macro de artículo en los tres pliegues en **al menos 0,02** y no sube la tasa de falsas alarmas en más de 2 puntos.
- **Si la mejora es menor de 0,02,** se elige la opción más simple o más barata.
- **Un brazo de ablación se adopta** solo si mejora F1 en al menos dos de los tres pliegues.
- **Un cambio a la vez.** Cada experimento cambia una sola cosa respecto a la configuración ganadora anterior.
- **La prueba congelada se usa una sola vez,** con los modelos finales, la calibración y la combinación ya fijados. Su resultado se informa tal como salga.

## 7. Formato común de predicciones

Cada corrida, de cualquier modelo, entrega `predicciones.csv` con estas columnas, para que el evaluador común las lea igual:

| Columna | Descripción |
| --- | --- |
| `id_fragmento` | Del conjunto común |
| `modelo` | `bilstm`, `mbert`, `beto`, `roberta_bne`, `xlmr`… |
| `configuracion` | Nombre corto de la configuración |
| `semilla` | 42, 43 o 44 |
| `pliegue` | F1, F2, F3 o `congelada` |
| `logit_real`, `logit_falsa` | Salidas crudas del modelo |
| `prob_falsa` | Softmax sin calibrar |

El evaluador común (lo construye Orlando) calcula todas las métricas de la sección 4.3 a partir de estos archivos. Así los dos modelos se miden con el mismo código.

## 8. Orden de trabajo

| Paso | Quién | Entregable |
| --- | --- | --- |
| 1. Construir `comun_v1` y su manifiesto | Orlando | `datasets/comun_v1/` |
| 2. Construir el evaluador común y las dos referencias | Orlando | Script + métricas de referencia |
| 3. Experimentos de cada modelo (en paralelo) | Orlando (BiLSTM) y responsable de mBERT | `predicciones.csv` por corrida |
| 4. Calibración y combinación | Orlando | `T` por modelo, coeficientes de combinación, tabla de niveles |
| 5. Prueba congelada, una sola vez | Orlando con las predicciones de ambos | Informe final |
| 6. Actualizar contratos del backend | Orlando | Configuración nueva de cada modelo |

## 9. Qué se puede esperar

- **Las cifras de validación bajarán** respecto al 0,77 / 0,94 actuales. La validación por fuente es más dura y, por eso, honesta.
- **El F1 en fuentes no vistas** puede subir algunos puntos. Sin datos nuevos no cabe esperar un salto grande.
- **Los niveles de la extensión** sí pueden pasar a decir la verdad, y eso no depende de subir el F1.
- **Ninguna mejora convierte al clasificador en un verificador de hechos.** Detecta parecido con los textos de entrenamiento.
