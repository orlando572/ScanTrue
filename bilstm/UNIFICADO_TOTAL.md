# Conjunto unificado de los datos locales

Generado con `bilstm/.venv/bin/python bilstm/unificar_todos.py`. Se leyeron las fuentes descargadas en `datasets/servir_directamente`, `datasets/no_directamente` y `datasets/MIS DATASETS`. No se entrenó ningún modelo. Los archivos originales, los modelos y el README principal permanecen intactos.

## Resultado de esta ejecución

| Archivo en `datasets/unificado_total/` | Filas | Contenido |
| --- | ---: | --- |
| `todos_los_textos_unicos.csv` | 76 948 | Un texto por contenido normalizado; contiene también tareas distintas de noticias binarias. |
| `noticias_binarias.csv` | 59 699 | Noticias con etiqueta directa: 25 172 falsas (`0`) y 34 527 reales (`1`). |
| `binarios_ampliados.csv` | 61 387 | Noticias anteriores más 1 688 textos binarios nuevos del corpus derivado USMSC/Edds, identificados como `binario_derivado`. |
| `factores_evidencias.csv` | 571 | Relaciones entre afirmación y evidencia de FactOReS. |
| `flares_anotaciones.csv` | 10 132 | Anotaciones de FLARES, separadas de los textos únicos. |
| `reporte.json` | — | Conteos, duplicados y correspondencia entre copias. |

Las 76 948 filas se desglosan en 59 699 noticias binarias directas, 1 688 textos binarios derivados, 2 487 afirmaciones falsas sin clase real equivalente, 13 073 textos de otras tareas y un caso con etiquetas contradictorias. **El archivo de todos los textos no se debe entrenar directamente como clasificador binario.** El archivo ampliado permite probar la inclusión del material derivado en un experimento posterior. Ningún resultado de desempeño se puede inferir del número de filas.

## Revisión de cada fuente

| Fuente original o variante | Campos y etiquetas relevantes | Decisión |
| --- | --- | --- |
| Spanish Political Fake News (57 231 filas) | `Titulo`, `Descripcion`, `Label`, `Fecha`; etiqueta `0/1`. | Se conserva titular y descripción completos. Aporta 56 764 textos principales tras deduplicar. Hay un texto idéntico con dos etiquetas y se aísla como conflicto. |
| Spanish Fake News Corpus v1, de jpposadas | `Headline`, `Text`, `Category`, `Link`, `Source`; `fake/true`. | Se usan los archivos de entrenamiento y desarrollo. La copia de prueba en FakeDeS se procesa como tal. |
| FakeDeS IberLEF 2021 | `HEADLINE`, `TEXT`, `CATEGORY`, `LINK`, `SOURCE`; `False/True`. | Noticias binarias, con procedencia de prueba. También corresponde al `test.xlsx` de jpposadas. |
| Spanish Fake and Real News, de Acosta | `texto`, `clase`; `fake/real`. | Noticias binarias de train y test; se eliminan coincidencias de contenido con otras fuentes. |
| FalleDesinfo ES | `Titular`, `Bajada`, `Cuerpo`, `Tipo de noticia`. | Se aplica la conversión binaria ya usada en el proyecto (`T1=0`, `T2/T3=1`); se mantiene identificada la tarea especializada. |
| PolyglotFakeFacts v2 | `news headline`, `news original text`, `language`, `label`, `url`, `domain`; `fake/real`. | Solo filas `Spanish` de `80.xlsx` y `20.xlsx`. `Fake.xlsx` y `Real.xlsx` son vistas por clase de esas particiones, no ejemplos nuevos en español. |
| Spanish Fake News Dataset de Zenodo | `Fake statement`, `Headlines`, URL, fecha y medio. | Afirmaciones falsas sin clase real comparable; permanecen en el conjunto maestro, separadas de noticias binarias. |
| FakeCovid | `source_title`, `content_text`, `class`, `lang`, fuente de verificación. | Se conservan artículos españoles de verificación. Su texto explica o desmiente otra afirmación: la etiqueta no describe la veracidad del artículo. |
| FactOReS | `claim`, `question`, `summarized_text`, `relevance`, `STANCE`, `label`. | 81 identificadores de afirmación se reducen a 78 textos únicos. Las 571 relaciones de evidencia se conservan aparte porque una afirmación puede tener varias etiquetas según la evidencia. |
| RUN-AS | `TITLE`, `TEXT`, `VALUE`. | Etiqueta de fiabilidad, separada de veracidad factual. |
| FLARES 2024 | `Text`, `Reliability_Label`, `5W1H_Label`, `Tags` y fragmentos. | 2 249 textos únicos en la tabla maestra; las 10 132 anotaciones quedan en archivo auxiliar. Las anotaciones no equivalen a 10 132 noticias. |
| USMSC y variante Edds | `text`, `label`; `0/1/2`, donde `2` es sátira. | Mismas 61 674 etiquetas en el mismo orden. Se detectaron y retiraron 50 997 textos derivados de fuentes ya presentes. Se conservan 1 688 binarios nuevos y 8 985 sátiras únicas; la sátira no se recodifica como falsa. |
| `MIS DATASETS/jpposadas`, `sayalaruano`, `gabrielhuav`, `nagorebravo` | Copias XLSX/CSV de jpposadas, USMSC y FactOReS. | La rutina verifica equivalencia de contenido o SHA-256 antes de evitar que estas copias se cuenten de nuevo. |
| MM-COVID | Solo existe un aviso de descarga pendiente. | No hay registros locales que agregar. |

## Cómo se quitaron los duplicados

Se compara el texto completo con una huella que ignora mayúsculas, acentos, puntuación y espacios. Para USMSC/Edds se compara además con las **descripciones originales sin titular**, porque ese corpus derivado eliminó titulares de algunas fuentes. Tres pares adicionales con la misma URL, etiqueta coincidente y contenido muy parecido se unieron conservando ambas procedencias. El reporte registra 8 945 registros repetidos por contenido y tres pares por URL. Las paráfrasis o artículos sobre el mismo hecho con distinto texto pueden permanecer: eliminarlos automáticamente podría unir noticias diferentes.

Cada fila conserva `datasets_origen`, `archivos_origen`, `particiones_origen`, etiqueta original y `grupo_uso`. Si etiquetas binarias del mismo texto discrepan, la fila queda en `conflicto` y fuera de los archivos binarios. La columna `idioma_declarado` refleja la selección española de cada fuente; no es una certificación automática de idioma para cada fila.

## Límite para el siguiente experimento

Las noticias del corpus político siguen dominando el subconjunto binario (aproximadamente el 95 %). Además, el conjunto ampliado incorpora datos que antes estaban reservados como prueba. Si después se entrena con todo, habrá que construir una **prueba externa nueva**, sin textos ni derivados compartidos, y publicar métricas por fuente y tipo de noticia. Este paso solo preparó los datos; no informa si un BiLSTM mejorará.
