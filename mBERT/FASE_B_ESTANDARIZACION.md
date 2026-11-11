# Fase B — estandarización y control de calidad

**Fecha:** 7 de octubre de 2026. **Estado:** preparación y verificación técnica terminadas. Las decisiones de exclusión, agrupación por evento y partición quedan para la fase C. No se entrenó ningún modelo.

## Entregables

- Datos normalizados: [normalized_all.jsonl.gz](../datasets/processed/phase_b_20261007_v1/normalized_all.jsonl.gz) (JSON Lines comprimido; 48 772 registros). Cada fila conserva texto original, texto limpio, etiqueta original y binaria, idioma declarado, dataset, archivo y fila de origen, URL, fuente, fecha disponible, licencia declarada y banderas de revisión.
- Resumen automatizado: [quality_report.json](../datasets/processed/phase_b_20261007_v1/quality_report.json).
- Comprobaciones de integridad: [verification_report.json](../datasets/processed/phase_b_20261007_v1/verification_report.json).
- Pares de titulares semejantes: [near_title_candidates.csv](../datasets/processed/phase_b_20261007_v1/near_title_candidates.csv).
- Casos prioritarios para adjudicar: [review_queue.csv](../datasets/processed/phase_b_20261007_v1/review_queue.csv), 108 filas. Un par se representa mediante `id` e `id_pareja`; contiene metadatos breves, no todo el texto.
- Scripts reproducibles: [prepare_phase_b.py](prepare_phase_b.py), [verify_phase_b.py](verify_phase_b.py) y [build_phase_b_review_queue.py](build_phase_b_review_queue.py). La preparación rechaza un directorio de salida ya existente para evitar sobrescrituras. Los originales de `datasets/raw` no fueron modificados.

Se utilizó el Python auxiliar de Codex para leer los `.xlsx` con `openpyxl`; el entorno `.venv` del proyecto no recibió instalaciones adicionales.

## Esquema y reglas

`etiqueta_binaria`: **0 = REAL**, **1 = FALSA**. Las etiquetas `True`/`real`/`legit` pasan a 0; `False`/`Fake`/`fake` pasan a 1. En el Excel español v2, `True` y `False` son valores booleanos y se mapearon de ese modo. Todas las 48 772 filas tienen etiqueta válida.

`texto_modelo` une titular y cuerpo con una línea vacía cuando existen ambos. Se decodifican entidades HTML, se retiran etiquetas HTML, se aplica Unicode NFC y se unifican espacios. Se conservan mayúsculas, tildes y puntuación. `titulo_original` y `cuerpo_original` permiten reconstruir la lectura; `titular` y `cuerpo` son la versión limpia. No se ha aplicado tokenización mBERT ni truncamiento: eso corresponde a la fase D.

Para Polyglot se leyeron únicamente `Fake.xlsx` y `Real.xlsx`, solo filas cuyo **idioma original declarado** es inglés o español. No se incorporaron las columnas de traducción ni los archivos alternativos `20.xlsx` y `80.xlsx`. Se excluyeron 8 855 filas de otros idiomas antes de normalizar. El campo de idioma es una declaración de origen, no una verificación lingüística independiente.

| Dataset | Idioma | REAL | FALSA | Total |
| --- | --- | ---: | ---: | ---: |
| Español v1 | es | 491 | 480 | 971 |
| Español v2 | es | 286 | 286 | 572 |
| ISOT | en | 21 417 | 23 481 | 44 898 |
| Pérez-Rosas | en | 490 | 490 | 980 |
| Polyglot | es | 480 | 289 | 769 |
| Polyglot | en | 137 | 445 | 582 |
| **Total** | | **23 301** | **25 471** | **48 772** |

**Nota:** el total de reales es 23 301 y falsos 25 471; cada caso aparece una sola vez en la tabla, aunque algunos textos son repetidos.

## Calidad y riesgos detectados

- **Duplicación exacta:** 5 318 grupos con más de un registro; abarcan 11 148 filas. Esos registros están señalados, sin borrarlos. No se encontraron grupos de texto exacto con etiquetas opuestas ni entre distintos datasets. Hay **4 grupos** que cruzan `train` y `development` de español v1. Hay 11 grupos de URL repetida y ninguno con etiquetas opuestas. La huella usa cuerpo limpio o titular cuando falta cuerpo, en minúsculas y con espacios uniformes; no detecta paráfrasis.
- **Similitud de titulares:** 646 pares candidatos, sin fusión automática. **4 pares cruzan español v1 y v2**; la inspección de titulares y URL indica probable reutilización de la misma noticia. **8 pares** tienen etiquetas distintas, todos dentro de Pérez-Rosas; algunos parecen pares creados deliberadamente para cambiar la afirmación. La similitud de titulares es una búsqueda de alta precisión y **no descarta** otros solapamientos por evento, cuerpo o traducción. Los 4+8 pares figuran en la cola de revisión.
- **Campos faltantes y longitud:** 73 titulares y 663 cuerpos vacíos; 1 713 textos tienen menos de 50 palabras. La mediana de palabras en `texto_modelo` es 328 para español v1, 411 para v2, 375 para ISOT, 160 para Pérez-Rosas y 616 para Polyglot. El percentil 90 es 659, 1 026, 758, 467 y 1 800, respectivamente. Estas son palabras aproximadas (`split`), **no tokens de mBERT**. La fase D medirá pérdida real por longitudes 128, 192, 256 y, si procede, 512.
- **Tipo de texto en español v2:** los autores indican 90 publicaciones sociales falsas, pero el archivo no tiene una columna que las identifique inequívocamente. Hay exactamente 90 filas con `fuente=AFPFactual`, todas falsas, pero no se asume que sean las mismas 90 publicaciones; esas filas quedan para revisión. 39 URL de v2/otros registros apuntan a plataformas sociales. Ninguna fila de v2 se marca definitivamente como «artículo» por este indicio.
- **Idioma Polyglot:** 2 registros declarados `en` tienen más del 15 % de letras no latinas. Quedan señalados; la heurística no garantiza que todos los demás sean inglés/español correcto. Se debe revisar idioma, especialmente antes de usar Polyglot como evaluación.
- **Sesgo de fuente y etiqueta:** los 480 ejemplos españoles reales de Polyglot proceden de `mundo.es`; entre sus falsos ingleses, 141 tienen fuente `rt english`. En español v1, fuentes como `El Dizque` (135) y `El Ruinaversal` (94) solo aportan falsos en esta muestra. En ISOT, 18 653 cuerpos empiezan con una dateline Reuters explícita; el origen del corpus ya advierte que la clase real se nutre de Reuters. Estas marcas pueden permitir atajos de clasificación. No corresponde presentar una puntuación interna alta como prueba de verificación factual.
- **Fechas:** se pudieron convertir 44 853 fechas de ISOT y 487 de Polyglot a ISO. El parser no aceptó las demás o no existían; se conserva siempre `fecha_publicacion_original` para revisión. Español v1/v2 y Pérez-Rosas no proporcionan fecha por fila en estos archivos.
- **Licencias y validez de etiquetas:** las licencias registradas son declaraciones de las fuentes de los corpus, no una autorización uniforme para redistribuir artículos. Las etiquetas se mapearon mecánicamente; no se verificó manualmente la veracidad factual de cada noticia.

## Decisión para la fase C

1. Mantener el `test` de español v2 **reservado**. Antes de medir métricas, resolver los 4 pares v1/v2 y los casos sociales; documentar qué IDs se excluyen o se analizan aparte. Conservar una versión inmutable del manifiesto de decisión.
2. Resolver las 4 coincidencias exactas `train`/`development` de v1 sin permitir que el mismo texto cruce entrenamiento y validación. La cola registra el ID del registro de desarrollo y su par de entrenamiento.
3. Agrupar o revisar los 8 pares de titulares con etiquetas opuestas de Pérez-Rosas antes de cualquier división de ese corpus; no cambiar etiquetas por coincidencia de título.
4. No usar el subconjunto español de Polyglot como **prueba externa balanceada principal** tal como está: todos los 480 reales comparten fuente. Puede servir como prueba de estrés con esa limitación explícita, o se debe localizar otra evaluación española independiente. La prueba principal prevista sigue siendo v2, tras limpiar fugas y separar tipos.
5. Diseñar particiones por grupo de texto/evento, URL y, donde sea posible, fuente/tiempo. Las banderas son insumos para decidir, no una exclusión automática. Registrar IDs, motivos y recuentos de cada decisión. Mantener ISOT y Pérez-Rosas separados de la prueba principal española.

La preparación de la fase B está cerrada. **No hay particiones definitivas ni datos aprobados para entrenamiento**; esos son los entregables de la fase C. No se requiere una descarga manual para completar lo realizado aquí.
