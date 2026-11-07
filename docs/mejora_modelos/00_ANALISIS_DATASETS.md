# Análisis de los datasets disponibles

**Fecha:** 7 de noviembre de 2026
**Alcance:** todos los datasets descargados en `DATASETS/`, `datasets/MIS DATASETS/`, `datasets/servir_directamente/`, `datasets/no_directamente/` y `datasets/pruebas_externas/`, más los conjuntos derivados que ya usaron los modelos. Las cifras se calcularon sobre los archivos locales con `bilstm/.venv`. No se modificó ningún archivo de datos.

Documento siguiente: [01_PLAN_COMUN.md](01_PLAN_COMUN.md).

## 1. Resumen

- **Hay un solo dataset por fuente, aunque aparezca en varias carpetas.** `DATASETS/` es una copia idéntica de `datasets/MIS DATASETS/`, y esta repite archivos de `servir_directamente/` y `no_directamente/` (USMSC, v1 y FakeDeS son byte a byte iguales).
- **Solo tres fuentes aportan artículos reales y falsos comparables:** Spanish Fake News Corpus v1, FakeDeS y PolyglotFakeFacts (español). Tras quitar sátira y redes sociales suman **1.960 artículos (705 falsos y 1.255 reales)**. Ese es el techo real de datos para la tarea.
- **Las dos fuentes grandes no son artículos:**
  - La fuente política (56.763 filas) es titular + entradilla (mediana de 52 palabras), y sus falsas se fabricaron **cambiando nombres en noticias reales**.
  - USMSC/Edds residual (1.687 filas) son textos **cortados a 300 caracteres**, sin fuente ni URL.
- **Hay tres atajos fuertes en los datos:**
  1. **Medio:** casi cada dominio aporta una sola clase (100 % en Polyglot).
  2. **Sátira:** la mayoría de las falsas de v1 vienen de sitios de sátira.
  3. **Longitud:** las falsas son más cortas que las reales. Un clasificador que **solo cuenta palabras** obtiene F1 macro **0,663** en la prueba externa de 606, más que el BiLSTM (0,603) y que mBERT (0,600).
- **La búsqueda web no encontró corpus nuevos** de artículos en español con ambas clases. Lo que existe son colecciones de afirmaciones o copias de lo que ya tienes (sección 6).

## 2. Inventario y duplicados entre carpetas

| Carpeta | Contenido | Relación con el resto |
| --- | --- | --- |
| `DATASETS/` | Edds, USMSC (gabrielhuav), jpposadas (v1 + FakeDeS), sayalaruano (v1), FactOReS | **Copia idéntica** de `datasets/MIS DATASETS/` (comprobado con `diff -r`) |
| `datasets/MIS DATASETS/` y `.zip` | Lo mismo que arriba | Los archivos de USMSC, v1 y FakeDeS son idénticos a los de `servir_directamente/` y `no_directamente/` |
| `datasets/servir_directamente/` | v1, fuente política, Acosta | Originales usados por el unificador |
| `datasets/no_directamente/` | FakeDeS, USMSC, Polyglot, FalleDesinfo, FakeCovid, Zenodo, FactOReS, RUN-AS, FLARES, MM-COVID (no descargado) | Originales de tareas distintas o solo de prueba |
| `datasets/pruebas_externas/x_fact/` | X-FACT original y su versión filtrada en español | Prueba de afirmaciones cortas |
| `datasets/unificado_total/` | 76.948 textos únicos de todas las fuentes, con `dataset_principal`, `tipo_tarea`, `url`, `fecha` y huellas | Punto de partida recomendado para el conjunto común |

**Recomendación:** tomar como fuente de verdad `datasets/servir_directamente/`, `datasets/no_directamente/` y `datasets/unificado_total/`. Las carpetas `DATASETS/` y `MIS DATASETS/` no aportan nada nuevo; se pueden archivar para no contar dos veces los mismos datos.

## 3. Perfil de cada fuente

Palabras contadas con espacios sobre `texto` (titular incluido cuando existe). Clase `0=falsa`, `1=real`, como en el unificado.

| Fuente | Filas | Falsas | Reales | Mediana de palabras | p10–p90 | URL | Tipo real del texto |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| Spanish Fake News Corpus v1 | 968 | 478 | 490 | 315 | 170–654 | 968 | Artículo completo |
| FakeDeS (v2, IberLEF 2021) | 571 | 286 | 285 | 410 | 161–1.028 | 568 | Artículo o publicación |
| PolyglotFakeFacts v2 (español) | 769 | 289 | 480 | 565 | 109–1.246 | 769 | Artículo completo |
| Spanish Political Fake News | 56.763 | 23.850 | 32.913 | 52 | 36–74 | 0 | Titular + entradilla |
| USMSC/Edds residual binario | 1.687 | 695 | 992 | 43 | 36–47 | 0 | Fragmento cortado a 300 caracteres |
| Acosta (Kaggle) | 595 | 258 | 337 | 334 | 149–620 | 0 | Artículo; falsas con sátira |
| FalleDesinfo_ES | 33 | 11 | 22 | 343 | 179–831 | 0 | Artículo, dos eventos |
| Zenodo (Tretiakov) | 2.488 | 2.488 | 0 | 40 | 14–244 | 1.186 | Afirmaciones falsas |
| X-FACT español estricto | 594 | 218 | 376 | — | 4–35 tokens | — | Afirmaciones cortas |
| FakeCovid | 1.681 | — | — | — | — | — | Artículos de verificación |
| FactOReS | 571 (81 afirmaciones) | — | — | — | — | — | Afirmación + evidencia, 3 clases |
| RUN-AS | 80 | — | — | — | — | — | Fiabilidad percibida |
| FLARES 2024 | 2.248 fragmentos | — | — | — | — | — | Fiabilidad por segmentos |

## 4. Hallazgos por fuente

### 4.1. Spanish Fake News Corpus v1: la mayoría de sus falsas son sátira

| Dominio | Falsas | Reales |
| --- | ---: | ---: |
| eldizque.com (sátira) | 135 | 0 |
| elruinaversal.com (sátira) | 94 | 0 |
| haynoticia.es (sátira) | 38 | 0 |
| censura0.com | 36 | 0 |
| elpais.com | 0 | 74 |
| eluniversal.com.mx | 1 | 67 |
| excelsior.com.mx | 0 | 45 |

- 141 dominios, de los cuales **solo 6 aportan ambas clases** (88 de 968 filas).
- Tras quitar los dominios de sátira ya identificados por la política de mBERT (`eldizque`, `elruinaversal`, `haynoticia`, `lavozpopular`, `elmundotoday`), **v1 conserva solo 167 falsas de 478**.
- **El BiLSTM seleccionado entrenó con 233 textos de sátira como «falsa»** (18 % de sus falsas). En su validación, 36 de las 81 falsas (44 %) eran sátira. Parte de su F1 de validación (0,765) mide «detectar sátira», no desinformación.

### 4.2. FakeDeS: casi todo separado por medio

- 213 dominios, 14 con ambas clases (118 de 571 filas).
- Las falsas incluyen `facebook.com` (24) y `perma.cc` (23, archivos de páginas).
- Las reales vienen de medios grandes (El País, El Universal, Milenio, BBC).
- **Mediana de palabras: 310 en falsas y 559 en reales.**

### 4.3. PolyglotFakeFacts (español): un detector de medios perfecto

- **Ningún dominio aporta ambas clases.** Las 480 reales son todas de `elmundo.es`; las falsas vienen de medios de propaganda (`news-front.info`, `russian.rt.com`, `sputnik`, `tsargrad.tv`…).
- Un modelo puede acertar aquí reconociendo a El Mundo, sin entender nada de veracidad.
- Mediana de palabras: 419 en falsas y 604 en reales.

### 4.4. Spanish Political Fake News: falsas sintéticas por sustitución de nombres

Al comparar titulares y finales de texto, **9.933 titulares aparecen en ambas clases** (20.589 filas) y 18.053 finales de texto también (36.512 filas). Ejemplo real del corpus:

> **Real:** «…Los comisionistas del escándalo de las masacrillas [sic] en Madrid, **Luis Medina y Alberto Luceño**, han declarado…»
> **Falsa:** «…Los comisionistas del escándalo de las masacrillas [sic] en Madrid, **Soledad Luque y Ernesto Alba**, han declarado…»

Consecuencias:

- **Es otra tarea:** detectar un nombre cambiado, no reconocer desinformación real.
- **Explica el 0,937 interno del modelo de 46.795 filas:** las parejas real/falsa no se agruparon, así que el modelo veía en prueba la gemela de lo que había entrenado.
- **No sirve para la extensión:** con 52 palabras de mediana, casi ninguna fila llega al mínimo de 100 tokens que exige el backend.
- **Las fechas no son un atajo:** ambas clases cubren 2018–2023 con proporciones parecidas.

### 4.5. USMSC/Edds residual: fragmentos truncados sin procedencia

- Longitud casi constante (36–47 palabras), cortados a mitad de palabra («…según el registro de afiliados a la Segur»).
- Sin URL, fuente, fecha ni titular. No se puede auditar su etiqueta ni su medio.
- En mBERT subieron la F1 de validación, pero esa validación es poco fiable (ver [01_PLAN_COMUN.md](01_PLAN_COMUN.md)).

### 4.6. Acosta: sátira dentro de las falsas

Ejemplo de falsa: «Un orangután gana el Premio Planeta de los Simios 2016». Sin URL no se puede filtrar la sátira por dominio, y USMSC declara incluir este corpus. Ya estaba excluido de los conjuntos depurados; se mantiene así.

### 4.7. Fuentes de otras tareas

Zenodo y X-FACT son **afirmaciones** (el primero solo tiene falsas). FakeCovid son artículos que verifican afirmaciones, y su etiqueta describe la afirmación, no el artículo. FactOReS, RUN-AS y FLARES miden verificación con evidencia o fiabilidad. **Ninguna sirve para entrenar el clasificador binario de artículos.** X-FACT tampoco sirve para probar la extensión: sus textos (4–35 tokens) no llegan al mínimo de 100.

## 5. Los atajos, medidos

### 5.1. Medio

| Fuente | Filas en dominios de una sola clase |
| --- | ---: |
| v1 | 880 / 968 (91 %) |
| FakeDeS | 453 / 571 (79 %) |
| Polyglot | 769 / 769 (100 %) |

### 5.2. Longitud

Mediana de palabras por clase en los conjuntos del BiLSTM seleccionado (`experimentos_balanceados/pequeno_mejorado/`):

| Partición | Falsas | Reales |
| --- | ---: | ---: |
| Entrenamiento | 49 | 47 |
| Validación | 288 | 415 |
| Prueba | 274 | 408 |
| Externa (606) | 312 | 544 |

**Clasificador de solo longitud** («real si tiene más de 364 palabras», umbral elegido en validación):

- Validación: F1 macro 0,635.
- **Externa: F1 macro 0,663 y AUC 0,717**, por encima del BiLSTM (0,603) y de mBERT (0,600).

El BiLSTM no aprovecha este atajo porque solo lee 192 tokens: la correlación entre su `prob_falsa` y la longitud es −0,06. Pero significa que **la prueba externa premia la longitud del artículo**, algo que la extensión no recibe: el usuario envía un fragmento. La solución está en [01_PLAN_COMUN.md](01_PLAN_COMUN.md): entrenar y evaluar con fragmentos cuyo tamaño se decide sin mirar la clase.

### 5.3. Sátira

En los datos del BiLSTM seleccionado, todas las filas de sátira son «falsa»: 233 en entrenamiento, 36 en validación, 33 en prueba y 8 en la externa.

## 6. Búsqueda de datasets adicionales

Se buscó en Hugging Face, Kaggle, GitHub, Zenodo y actas de IberLEF/LREC. Resultado:

| Recurso | Qué es | ¿Aporta artículos reales y falsos nuevos? |
| --- | --- | --- |
| [mariagrandury/fake_news_corpus_spanish](https://huggingface.co/datasets/mariagrandury/fake_news_corpus_spanish) | 572 filas de FakeDeS | No: es FakeDeS |
| [sayalaruano/FakeNewsCorpusSpanish](https://huggingface.co/datasets/sayalaruano/FakeNewsCorpusSpanish) | Corpus v1 | No: ya está en `MIS DATASETS` |
| [FakeNews Español (Kaggle)](https://www.kaggle.com/datasets/guillermoezquer/fakenews-espaol) | Unión de corpus españoles, licencia desconocida | Probablemente no: unifica los mismos corpus |
| [FakesStorage](https://github.com/alcorpas10/FakesStorage) | Bulos de Maldita, Newtral y FactCheck.org | No: solo falsas, en formato de bulo |
| [MultiClaim (Zenodo)](https://zenodo.org/records/7737983) | 206 k verificaciones y 28 k publicaciones en 39 idiomas | No: afirmaciones y publicaciones, otra tarea |
| [Narrativaai/fake-news-detection-spanish](https://huggingface.co/Narrativaai/fake-news-detection-spanish) | Modelo RoBERTa entrenado con FakeDeS | No es un dataset; sirve como referencia |

Confirma lo que ya se sabía: **no hay corpus nuevos de artículos españoles con ambas clases**. No se descargó nada. Si en algún momento se quiere un conjunto de afirmaciones cortas, MultiClaim filtrado a español es el candidato, pero queda fuera del alcance de este plan porque la extensión no acepta textos tan cortos.

## 7. Conclusión: qué datos usar

| Fuente | Papel recomendado |
| --- | --- |
| v1 (sin sátira) | Conjunto común: entrenamiento y validación por fuente |
| FakeDeS (sin sátira ni redes) | Conjunto común: entrenamiento y validación por fuente |
| Polyglot español | Conjunto común con peso limitado; sus resultados se leen con cautela por la separación total de medios |
| Sátira de v1 | Fuera del conjunto principal (decidido el 7 de noviembre de 2026); solo en brazo de ablación |
| Fuente política | Fuera del conjunto principal; brazo de ablación con parejas agrupadas |
| USMSC/Edds residual | Fuera del conjunto principal; brazo de ablación |
| Acosta | Fuera |
| FalleDesinfo_ES | Solo prueba congelada |
| Zenodo, X-FACT, FakeCovid, FactOReS, RUN-AS, FLARES | Fuera: son otras tareas |

**Pool principal:** 1.960 artículos (705 falsos y 1.255 reales), de los cuales 92 tienen menos de 100 tokens. Cortados en fragmentos de 100–400 tokens con un máximo de 4 por artículo, dan **entre 4.000 y 5.000 fragmentos**, con unas 2 reales por cada falsa. Es poco, pero es el material limpio disponible, y es el mismo para los dos modelos.
