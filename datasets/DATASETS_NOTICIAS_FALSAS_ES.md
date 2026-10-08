# Datasets y corpus abiertos relacionados con noticias falsas en español

**Revisado:** 6 de octubre de 2026.

Reuní **13 recursos distintos** y descargué los archivos que tenían enlaces públicos funcionales. Los ordené en dos carpetas: `servir_directamente/` contiene texto en español con etiquetas fake/real y particiones de entrenamiento utilizables; `no_directamente/` contiene conjuntos que requieren filtrar idioma, armonizar etiquetas, son solo de prueba o miden otra tarea. Los archivos grandes y los datasets se mantienen ignorados por Git según la configuración del proyecto.

**Estado:** hay archivos locales de 12 de los 13 recursos. El CSV de Zenodo ya está en `no_directamente/spanish_fake_news_dataset_zenodo/`. MM-COVID sigue pendiente porque el enlace público de Google Drive del repositorio devuelve 404.

## Corpus más directos para fake/real

### 1. Spanish Fake News Corpus v1 (MEX-A3T 2020)

- **URL:** https://github.com/jpposadas/FakeNewsCorpusSpanish
- **Descarga:** los archivos `train.xlsx`, `development.xlsx` y `test.xlsx` están en el repositorio. También se pueden obtener con **Code → Download ZIP**.
- **Contenido:** 971 noticias (491 reales y 480 falsas), texto completo, titular, fuente, tema y URL.
- **Licencia indicada:** CC BY 4.0.
- **Nota:** corpus pequeño pero apropiado para una primera línea base.
- **Clasificación local:** sirve directamente. Archivos descargados en `servir_directamente/spanish_fake_news_corpus_v1/` (`train.xlsx`, `development.xlsx`).

### 2. FakeDeS (Spanish Fake News Corpus v2, IberLEF 2021)

- **URL:** https://github.com/jpposadas/FakeNewsCorpusSpanish
- **Descarga:** el archivo `test.xlsx` se encuentra en el mismo repositorio; consulta el README.
- **Contenido:** 572 publicaciones etiquetadas true/fake; incluye artículos y 90 posts falsos de redes sociales. Considera varias variantes de español, incluidas fuentes de Perú.
- **Licencia indicada:** CC BY 4.0.
- **Nota:** es una edición distinta dentro del mismo repositorio que v1 y contiene 572 ejemplos. El archivo disponible en el repo es el split `test.xlsx`; lo mantengo fuera del entrenamiento para poder usarlo como evaluación externa y evitar fuga de datos.
- **Clasificación local:** no directamente para entrenar; queda como prueba aparte en `no_directamente/fakedes_iberlef_2021/test.xlsx`.

### 3. Unified and Balanced Spanish Fake News Corpus (USMSC)

- **URL:** https://huggingface.co/datasets/gabrielhuav/Unified-and-Balanced-Spanish-Fake-News-Corpus
- **CSV principal:** https://huggingface.co/datasets/gabrielhuav/Unified-and-Balanced-Spanish-Fake-News-Corpus/blob/main/gabrielhuav_Unified_Spanish_Misinformation_and_Satire_Corpus_USMSC.csv
- **Descarga:** pública desde **Files and versions** en Hugging Face.
- **Contenido y licencia declarados en la ficha:** 61.674 registros; clases `FAKE`, `REAL` y `SATIRE`; MIT.
- **Nota:** la vista previa del archivo tiene un error de lectura. Comprueba el CSV y sus etiquetas antes de entrenar; no unas los espejos sin comparar duplicados.
- **Clasificación local:** no directamente para un problema binario; usa tres clases (fake/real/satire) y reúne fuentes presentes por separado. Queda fuera del primer unificado para evitar solapamiento. Descargado en `no_directamente/usmsc/usmsc.csv`.

### 4. PolyglotFakeFacts v2.0 (multilingüe; incluye español)

- **URL/DOI:** https://data.mendeley.com/datasets/8yfrm6z9dx/1
- **Descarga:** gratuita desde **Download All** en Mendeley Data.
- **Contenido declarado:** 10.206 artículos en 18 idiomas, entre ellos español, etiquetados `fake`/`non-fake`; incluye el texto original y su traducción al inglés.
- **Licencia indicada:** CC BY 4.0.
- **Nota:** la ficha no especifica cuántos casos son en español. Filtra por idioma y valida etiquetas, balance y fuentes.
- **Clasificación local:** no directamente; primero hay que filtrar `language=Spanish` y elegir el campo de texto. Descargados los cuatro XLSX en `no_directamente/polyglotfakefacts_v2/`. El unificado usa `80.xlsx` y `20.xlsx`; `Fake.xlsx` y `Real.xlsx` contienen los mismos ejemplos organizados por etiqueta.

### 5. Spanish Political Fake News

- **URL:** https://www.kaggle.com/datasets/javieroterovizoso/spanish-political-fake-news
- **Acceso:** dataset público en Kaggle; puede requerir cuenta gratuita para descargar.
- **Contenido:** noticias políticas en español etiquetadas para clasificación de desinformación; se describe como dataset para entrenamiento y evaluación.
- **Licencia:** verifica la licencia y condiciones visibles en Kaggle antes de reutilizarlo; no pude confirmar el texto de la ficha mediante la consulta automatizada.
- **Nota:** enfocado en política. El CSV descargado tiene 57.231 filas, con `Label=0` falsa y `Label=1` real; texto repartido entre `Titulo` y `Descripcion`. El artículo que describe el corpus explica que parte de las falsas se generó modificando noticias reales; el modelo podría aprender esos cambios artificiales. Usa evaluación por fuente/fecha y confirma licencia antes de redistribuir.
- **Clasificación local:** sirve directamente como corpus binario de entrenamiento. Archivo: `servir_directamente/spanish_political_fake_news/D57000_complete.csv`.

### 6. FakeCovid

- **URL:** https://github.com/Gautamshahi/FakeCovid
- **Descarga:** repositorio público con datos en la carpeta `data`.
- **Contenido:** corpus de verificaciones sobre COVID-19, con miles de artículos, 40 idiomas y etiquetas de veracidad/categoría; la licencia del repositorio indica CC0-1.0.
- **Nota:** corpus temático y multilingüe. Filtra los registros en español y agrupa sus etiquetas de verificación con cuidado antes de convertirlas a fake/real.
- **Clasificación local:** no directamente; requiere filtrar idioma y transformar sus etiquetas. Descargados los CSV de `data/` en `no_directamente/fakecovid/`.

### 7. MM-COVID

- **URL:** https://github.com/bigheiniu/MM-COVID
- **Datos:** el README enlaza archivos JSON públicos en Google Drive, con contenido y etiqueta de noticias verificadas.
- **Contenido:** noticias y contexto social relacionados con desinformación de COVID-19 en varios idiomas, incluido español según el artículo del corpus.
- **Licencia/condiciones:** confirma las condiciones de reutilización de los archivos vinculados; el repositorio no deja clara una licencia de datos.
- **Nota:** requiere filtrar idioma y procesar por separado noticias y tweets; algunos tweets solo están representados por IDs. El enlace de Google Drive que ofrece el README ahora responde 404.
- **Clasificación local:** no descargado; la fuente de datos indicada está rota. Revisa el README en `https://github.com/bigheiniu/MM-COVID` por si publican un enlace nuevo.

## Datasets de afirmaciones falsas o verificadas

### 8. Spanish Fake News Dataset (Tretiakov et al.)

- **URL/DOI:** https://doi.org/10.5281/zenodo.15592391
- **Descarga:** el registro público de Zenodo contiene `esp_fake_news.csv` y un README descargables.
- **Contenido:** afirmaciones falsas en castellano recogidas de fuentes de verificación como Maldito Bulo, Newtral y AFP Factual. Incluye titulares, afirmaciones y ejemplos de varios formatos.
- **Licencia del registro:** CC BY 4.0. La descripción también dice que el dataset está destinado a investigación académica no comercial; ante esa diferencia, confirma con los autores qué condiciones aplicar antes de cualquier uso comercial.
- **Nota:** no es un corpus equilibrado de noticias verdaderas y falsas. No etiquetes cada fila como noticia completa; inspecciona las columnas y diseña la tarea en función de su contenido.
- **Clasificación local:** no directamente para clasificación binaria; contiene sobre todo titulares/afirmaciones falsas. `esp_fake_news.csv` está descargado en `no_directamente/spanish_fake_news_dataset_zenodo/` y contiene 2.552 filas. El README del registro aún no está descargado. No añadas etiquetas “reales” inventadas.

### 9. FactOReS (Fact-checking with an Evidence-based Open Resource in Spanish)

- **URL:** https://github.com/hitz-zentroa/AFC_FactOReS
- **Descarga:** pública en el repositorio; incluye datos y guía.
- **Contenido:** 571 afirmaciones en español con pregunta de verificación, evidencia y etiqueta `Supported`, `Refuted` o `Not Enough Evidence`.
- **Licencia de datos indicada:** CC BY 4.0.
- **Nota:** es verificación basada en evidencia, no clasificación de artículos completos. Úsalo para clasificación de afirmaciones con tres clases o para experimentos auxiliares; no conviertas las etiquetas sin revisar el criterio.
- **Clasificación local:** no directamente para el objetivo binario de noticias; descargado `dev.json` en `no_directamente/factores/`.

## Corpus de fiabilidad relacionados (no equivalen exactamente a fake/real)

### 10. RUN / RUN-AS (Reliable and Unreliable News)

- **URL:** https://github.com/marionieto51/NewsReliabilityAnnotation
- **Descarga:** el repositorio público contiene `data.json` y la guía de anotación.
- **Contenido:** 80 noticias en español de salud/COVID. El archivo local contiene 53 `Reliable` y 27 `Unreliable`.
- **Nota:** es muy pequeño y la etiqueta expresa fiabilidad percibida a partir del texto; no es verificación factual definitiva. Úsalo para evaluación exploratoria o aprendizaje auxiliar. Revisa la licencia, que no aparece claramente indicada en la página del repositorio.
- **Clasificación local:** no directamente; descargado `data.json` en `no_directamente/run_as/`.

### 11. FLARES 2024

- **Ficha y acceso:** https://portal.odesia.uned.es/en/dataset/flares-2024
- **Descarga:** acceso público; la ficha enlaza el conjunto JSON.
- **Contenido:** 190 noticias españolas (133 train, 57 test) etiquetadas `reliable`, `partially reliable` o `unreliable`, además de segmentos que responden quién/qué/cuándo/dónde/por qué.
- **Nota:** estas categorías miden fiabilidad; no equivalen directamente a noticias falsas/verdaderas. Puede servir para clasificación de tres niveles y evaluación en un dominio distinto.
- **Licencia:** revisa las condiciones en la página de datos enlazada antes de reutilizar.
- **Clasificación local:** no directamente; mide tres niveles de fiabilidad y no fake/real. Descargados sus cuatro JSON de entrenamiento/prueba en `no_directamente/flares_2024/`.

## Nuevos corpus descargados de noticias en español

### 12. Spanish Fake and Real News (Fabricio A. Zules Acosta)

- **URL:** https://www.kaggle.com/datasets/zulanac/fake-and-real-news
- **Licencia declarada en Kaggle:** CC BY-SA 4.0.
- **Archivos:** `spanishFakeNews.csv` (538 filas) y `testSpanishFakeNews.csv` (60 filas), con `texto` de noticia y `clase` (`fake` o `real`). En total hay 259 falsas y 339 reales. Se conservó también el ZIP original de la versión 8.
- **Clasificación local:** sirve directamente. Está en `servir_directamente/spanish_fake_and_real_news_acosta/`. Se respeta el segundo CSV como prueba. Tras retirar dos textos repetidos dentro del conjunto combinado, aporta 596 ejemplos al unificado.
- **Nota:** contiene noticias completas de distintas fuentes, sin campo temático explícito. USMSC declara incorporar este corpus; por eso se mantiene excluido del unificado. La nueva fuente mejora la variedad, pero no compensa por sí sola el predominio del corpus político.

### 13. FalleDesinfo_ES

- **URL/DOI:** https://doi.org/10.5281/zenodo.13127598
- **Licencia del registro:** CC BY 4.0.
- **Archivo:** `FalleDesinfo_ES.xlsx`, 33 noticias en español con fecha, titular, bajada, cuerpo y tipo. Las 11 de tipo `T1` difundieron por error el rumor de la muerte de Noam Chomsky; 11 `T2` lo desmintieron y 11 `T3` informaron de la muerte real de Stephen Hawking.
- **Clasificación local:** no directamente para aumentar entrenamiento: está en `no_directamente/falledesinfo_es/` y se reserva como prueba externa. Para la salida binaria se asigna `T1 → 0` y `T2/T3 → 1`, preservando el tipo original.
- **Nota:** es pequeño y todos sus ejemplos tratan dos fallecimientos; sus métricas no representan por sí solas el rendimiento en otras noticias.

## Recurso público que requiere inspección antes de contar como dataset de entrenamiento

### Proyecto SPR: Infodemia (México; listado de desmentidos)

- **URL:** https://www.datos.gob.mx/dataset/proyecto_spr_infodemia
- **Contenido descrito:** CSV público con noticias desmentidas entre 2022 y enero de 2026, desglosadas por fecha, tema, sección y subsección.
- **Nota:** la página respondió 403 a la consulta automatizada. No está confirmado que incluya texto completo o pares verdaderos/falsos; revisa el CSV y las condiciones antes de usarlo.
- **Clasificación local:** no descargado. En el portal prueba **Visualizar** y luego **Descargar**; inspecciona las columnas y los términos de reutilización antes de considerarlo corpus de entrenamiento.

## Archivos descargados y organización local

Los originales están en `servir_directamente/` y `no_directamente/`, cada dataset en su propia subcarpeta. Para leer los XLSX, instala/usa un lector de Excel en tu entorno Python; no cambié los originales.

## Acceso si la página no muestra el archivo

1. **GitHub:** entra al repositorio, abre el README y busca instrucciones de datos. Si los ficheros aparecen en la lista, puedes abrirlos allí; si no, usa **Code → Download ZIP**.
2. **Hugging Face:** abre **Files and versions** y descarga el archivo desde su menú. Si la vista previa falla, intenta la descarga directa desde esa pestaña y revisa el README/Dataset Card.
3. **Zenodo:** abre el DOI, baja a **Files** y descarga tanto el CSV como el README.
4. Si el enlace no funciona, busca el título exacto entre comillas junto con el nombre de sus autores o institución. Confirma que llegaste al repositorio oficial y revisa licencia y versión.

## Recomendación para el BiLSTM

El unificado actual usa Spanish Fake News Corpus v1, Spanish Political Fake News, Spanish Fake and Real News y la parte española de PolyglotFakeFacts para entrenamiento/validación. FakeDeS y FalleDesinfo_ES quedan en prueba externa. USMSC se conserva por separado porque reúne fuentes presentes en el proyecto. FactOReS y el dataset de Zenodo son afirmaciones, mientras RUN y FLARES miden fiabilidad; no son sustitutos directos de un corpus binario de artículos. El corpus político todavía aporta aproximadamente el 95 % del unificado: informa métricas por fuente y sigue buscando datos variados con etiquetas comparables.
