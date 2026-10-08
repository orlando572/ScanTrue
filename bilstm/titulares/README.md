# Experimento independiente: BiLSTM para titulares

Este modelo recibe **solo el titular** de una noticia en español. Sus datos,
pesos y resultados se guardan en `datasets/experimentos_titulares/` y
`datasets/modelos_titulares/`. El modelo principal de **192 tokens** sigue en
`datasets/modelos_bilstm/sin_politica/` y no se modifica.

## Datos y separación

`preparar.py` toma las particiones ya preparadas de la variante `sin_politica`,
conserva solo registros que tienen un titular real y pone ese titular en la
columna `texto`. No extrae las primeras palabras del cuerpo ni inventa
titulares. Mantiene las particiones originales, las etiquetas y las fuentes;
rechaza titulares idénticos dentro y entre particiones. Guarda hashes de los
CSV de origen en `manifest.json`.

| Partición | Titulares | Falsos | Reales | Fuentes |
| --- | ---: | ---: | ---: | --- |
| Entrenamiento | 1298 | 566 | 732 | Spanish Fake News Corpus v1, PolyglotFakeFacts v2 |
| Validación | 294 | 141 | 153 | Spanish Fake News Corpus v1 |
| Prueba | 675 | 283 | 392 | FakeDeS, PolyglotFakeFacts v2, FalleDesinfo ES |

Se omitieron 536 registros de entrenamiento y 132 de prueba sin titular. La
validación contiene una sola fuente; esto limita la elección del modelo. La
prueba ya se consultó durante este experimento y no debe servir para ajustar
sus hiperparámetros. Para una evaluación final hará falta otro conjunto nuevo.

## Entrenamiento y resultados

Se usó la arquitectura y los hiperparámetros del entrenamiento principal,
semilla 42, con límite de **64 tokens**. Los titulares presentes tienen como
máximo 30 tokens según el tokenizador del proyecto. La selección de la época
se hizo con validación, sin leer la prueba. El mejor checkpoint fue la época 4.

| Modelo sobre el mismo conjunto de titulares | Validación F1 macro | Prueba exactitud | Prueba F1 macro | Prueba recall «falsa» |
| --- | ---: | ---: | ---: | ---: |
| Principal de 192 tokens | 49,65 % | 53,19 % | 53,14 % | 67,14 % |
| Independiente de titulares, 64 tokens | **53,01 %** | 55,41 % | 53,22 % | 40,28 % |

La diferencia de F1 macro en prueba es mínima. El modelo nuevo detecta menos
noticias falsas, aunque reduce las noticias reales clasificadas como falsas:
132 de 392 reales frente a 223 de 392 con el modelo principal aplicado a
titulares. En FakeDeS, el F1 macro del modelo nuevo fue **46,71 %**; en
PolyglotFakeFacts, **78,02 %**. No hay una mejora general convincente ni una
base para desplegarlo como verificador de hechos.

Los resultados detallados están en
`datasets/modelos_titulares/sin_politica/{resultados,evaluacion_prueba}.json` y
la comparación en `datasets/modelos_titulares/comparacion_modelo_192_titulares.json`.

## Cómo repetirlo

Desde la raíz del proyecto, con el entorno de `bilstm` ya instalado:

```bash
bilstm/.venv/bin/python bilstm/titulares/preparar.py
bilstm/.venv/bin/python bilstm/entrenar.py \
  --input datasets/experimentos_titulares/sin_politica \
  --output datasets/modelos_titulares/sin_politica \
  --max-len 64 --validation-only --device cuda
bilstm/.venv/bin/python bilstm/titulares/evaluar.py --device cuda
```

El entrenamiento se detiene si la carpeta de salida ya contiene archivos;
para repetirlo, usa otra carpeta `--output`. `evaluar.py` acepta `--modelo`
para comparar cualquier checkpoint sobre **los mismos titulares**.

Para una predicción con el modelo independiente, pasa únicamente el titular:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py \
  --modelo datasets/modelos_titulares/sin_politica/mejor_modelo.pt \
  --referencia datasets/experimentos_titulares/sin_politica \
  --texto 'Aquí va el titular completo' --device cuda
```

`prob_falsa` es una puntuación del clasificador; no demuestra que la noticia
sea verdadera o falsa. Una noticia reciente requiere consultar fuentes y
evidencia actual.

## Datos que podrían ayudar después

- [Spanish Fake News Corpus / FakeDeS](https://github.com/jpposadas/FakeNewsCorpusSpanish):
  ya se utiliza aquí. No volver a agregarlo como si fueran ejemplos nuevos.
- [PolyglotFakeFacts v2](https://data.mendeley.com/datasets/8yfrm6z9dx/1):
  también está incorporado tras filtrar español; vigilar duplicados entre
  sus archivos de distribución.
- [USMSC](https://huggingface.co/datasets/gabrielhuav/Unified-and-Balanced-Spanish-Fake-News-Corpus):
  incluye varias fuentes ya presentes y una clase de sátira. Comparar
  registros y etiquetas antes de tomar ejemplos nuevos.
- [FakesStorage](https://github.com/alcorpas10/FakesStorage):
  recopila verificaciones de bulos; hay que comprobar que el título sea la
  afirmación original y reunir noticias reales comparables. No sirve como
  corpus binario directo si solo aporta falsedades.
- [X-FACT](https://huggingface.co/datasets/utahnlp/x-fact) y
  [FactOReS](https://github.com/hitz-zentroa/AFC_FactOReS):
  son recursos de verificación de **afirmaciones**; podrían servir para otro
  experimento con evidencia, tras filtrar idioma y mapear etiquetas con
  cuidado. No son titulares de noticias equivalentes a estos.
- [Colección UIB de verificaciones 2025–2026](https://portalinvestigacio.uib.eu/documentos/6aa87e4f1a685e7ecee8c6f4):
  candidata para estudiar afirmaciones recientes. Antes de usarla, inspeccionar
  qué representa cada título y cada veredicto y si hay ejemplos verdaderos y
  falsos utilizables.

La ampliación más útil será un corpus **nuevo**, con titulares originales de
noticias falsas y verdaderas verificadas, variedad temática y fechas recientes.
Conviene reservar parte por medio y fecha para medir generalización. No asignar
la etiqueta «real» solo porque un titular provenga de un medio conocido, ni
la etiqueta «falsa» al título de un artículo de verificación sin recuperar la
afirmación que ese artículo examina.
