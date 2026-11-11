# Fase F — evaluación en pruebas reservadas

**Estado:** completada el 7 de octubre de 2026. Se ejecutó una evaluación por checkpoint y partición con el [protocolo congelado](phase_f_plan_20261007_v1.json), umbral **0,5**, sin ajustar modelos, umbral ni calibración tras abrir las pruebas. El candidato elegido en fase E sigue siendo **E1, 256 tokens, semilla 44**; la prueba revela que **no está listo para uso real**.

## Datos y trazabilidad

Se evaluaron 8 checkpoints mBERT predefinidos (E1: 3 semillas; E2: 1; E3: 3; E4: 1) y tres líneas base TF‑IDF + regresión logística E0. Particiones congeladas: `es_test_main` (451; 284 REAL, 167 FALSA), `es_test_polyglot_stress` (750; 473 REAL, 277 FALSA) y `en_test_perez_rosas` (949). Los archivos de prueba se verificaron contra su manifiesto y se comprobó el SHA-256 del checkpoint seleccionado (`7e6a88893c10f0d9ea89ec6b9347e00f872f140ce2752b7fa00011ccb634ff5c`). [evaluate_phase_f.py](evaluate_phase_f.py) reproduce el preprocesamiento de fase D y usa la longitud guardada en cada ejecución. Se guardó todo en una carpeta nueva, sin sobrescribir los entrenamientos.

Los [resultados por ejecución](evaluations/phase_f_20261007_v1/results.csv), las [métricas JSON](evaluations/phase_f_20261007_v1), las [predicciones por ID](evaluations/phase_f_20261007_v1/predictions.csv.gz), la [curva precisión–recall](evaluations/phase_f_20261007_v1/selected_pr_curve.csv) y el [análisis descriptivo](evaluations/phase_f_20261007_v1/subgroups.csv) permiten revisar los cálculos. Las matrices usan filas **REAL, FALSA** y columnas **predicha REAL, predicha FALSA**; FP es una noticia real marcada falsa.

## Prueba española principal

| Modelo | F1 FALSA | Precisión | Recall | F1 macro | Exactitud | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **E1 seleccionado** (semilla 44) | **0,535** | 0,368 | 0,982 | 0,274 | 0,368 | **282** | 3 |
| E1 semilla 42 | 0,533 | 0,373 | 0,934 | 0,337 | — | — | — |
| E1 semilla 43 | 0,539 | 0,409 | 0,790 | 0,495 | — | — | — |
| E2 solo inglés | 0,207 | 0,583 | 0,126 | 0,488 | 0,643 | 15 | 146 |
| E3 mixto semilla 42 | 0,389 | 0,746 | 0,263 | 0,592 | — | — | — |
| E3 mixto semilla 43 | 0,391 | 0,676 | 0,275 | 0,588 | — | — | — |
| E3 mixto semilla 44 | 0,318 | 0,660 | 0,210 | 0,549 | 0,667 | 18 | 132 |
| E4 inglés→español | 0,560 | 0,393 | 0,970 | 0,385 | 0,435 | 250 | 5 |
| E0 TF‑IDF español | 0,531 | 0,587 | 0,485 | 0,645 | — | — | — |
| E0 TF‑IDF inglés | 0,451 | 0,359 | 0,605 | 0,455 | — | — | — |
| **E0 TF‑IDF mixto** | **0,599** | 0,567 | 0,635 | **0,670** | **0,685** | 81 | 61 |

El candidato E1 pasa de **F1 0,869 en validación española a 0,535 en prueba externa**. Su matriz es `[[2, 282], [3, 164]]`: clasifica casi todo como FALSA. La precisión de REAL es 0,400, su recall **0,007** y su F1 **0,014**; la exactitud balanceada es **0,495**. Incluso la regla trivial de llamar FALSA a todo tendría F1 FALSA ≈ **0,540** en esta prueba. La AP de E1 es **0,421** y Brier **0,424**; sus probabilidades no deben presentarse como riesgo calibrado. E0 mixto obtiene AP **0,629**, Brier **0,213** y matriz `[[203, 81], [61, 106]]`.

Las tres semillas E1 dan F1 **0,533 / 0,539 / 0,535** (media ≈ **0,536**). Las tres E3 dan **0,389 / 0,391 / 0,318** (media ≈ **0,366**). E4 supera numéricamente a E1 en F1 de esta prueba, pero marca 250 noticias reales como falsas, y **no se selecciona un nuevo checkpoint a partir de la prueba**. Añadir inglés no demostró mejora reproducible en validación y E2/E3 tuvieron bajo recall de FALSA en la prueba española. La línea base mixta supera al candidato mBERT tanto en F1 FALSA como en F1 macro; la comparación externa es descriptiva y tampoco autoriza una nueva selección sin otra prueba intacta.

## Generalización a otros corpus

| Modelo predefinido | Polyglot es: F1 FALSA | Polyglot es: FP / FN | Pérez‑Rosas en: F1 FALSA |
| --- | ---: | ---: | ---: |
| E1 seleccionado | 0,527 | 467 / 11 | 0,653 |
| E2 solo inglés | 0,028 | 1 / 273 | 0,583 |
| E3 mixto semilla 44 | 0,114 | 5 / 260 | 0,576 |
| E4 inglés→español | 0,518 | 433 / 29 | 0,657 |
| E0 mixto | 0,496 | 72 / 162 | 0,656 |

Estas pruebas se reportan por separado de la principal. En Polyglot, **473 de las 473 noticias reales** proceden de `mundo.es`; E1 marca 467 de ellas como falsas. Además, 235 de las falsas no tienen fuente registrada. La fuente y la etiqueta están muy asociadas, por lo que el corpus sirve como prueba de estrés. La validación inglesa casi perfecta de E2 en ISOT no se reproduce en Pérez‑Rosas (F1 0,583), consistente con un cambio de fuente, estilo o método de construcción.

## Errores, subgrupos e incertidumbre

En la prueba española principal, **285 de 451** predicciones E1 son erróneas: 282 FP y 3 FN. Entre las 192 noticias cuya fuente aparece por nombre exacto en el entrenamiento español, hay 167 reales y 25 falsas: E1 marca como falsas **165 de las 167 reales**. Entre las 259 de fuente nueva o no registrada, marca falsas las **117 reales**. De `El Universal` hay 27 reales y todas son FP; de `Milenio`, 25 reales y todas son FP. Estos conteos identifican el error; no prueban por sí solos que el modelo use la fuente como causa.

El [desglose por longitud](evaluations/phase_f_20261007_v1/subgroups.csv) da F1 FALSA 0,740 en <200 palabras (46 casos), 0,632 en 200–499 (209), 0,352 en 500–999 (136) y 0,338 en ≥1000 (60). Las clases se distribuyen de forma distinta entre bandas, así que no se atribuye la diferencia solo al truncamiento. Los 3 registros sin titular son falsos y se clasificaron correctamente. El corpus principal no ofrece fechas utilizables en los datos normalizados; no se puede evaluar período. La categoría de tipo textual está sin verificar para todos sus registros, y tema/fuente tienen muchos grupos pequeños. [main_errors.csv](evaluations/phase_f_20261007_v1/main_errors.csv) conserva IDs y metadatos de errores sin copiar cuerpos de artículos.

El remuestreo **emparejado por fuente** de 1.000 iteraciones con semilla 42 produjo para F1 E1 seleccionado un intervalo percentil 95 % **[0,435, 0,644]**, para E3 semilla 44 **[0,238, 0,392]** y para la diferencia E3−E1 **[−0,345, −0,104]**. Hay 194 nombres de fuente tras normalizar mayúsculas; alias y eventos relacionados pueden quedar en grupos separados. Son intervalos **descriptivos**, no una garantía de rendimiento futuro. El [JSON del remuestreo](evaluations/phase_f_20261007_v1/source_bootstrap.json) registra el método.

## Decisión al cerrar la fase

La evaluación exigida está completa, pero **ningún checkpoint mBERT queda validado para despliegue**. El candidato congelado E1 falla en noticias reales externas y ofrece probabilidades mal calibradas. Se conserva como resultado de investigación junto con todos los entrenamientos separados. No se cambia su umbral ni se sustituye por E4 o E0 usando esta prueba ya observada. Cualquier nueva versión necesitará revisar etiquetas, procedencia y similitud de eventos, rediseñar entrenamiento/validación con más diversidad de fuentes y reservar **una nueva prueba externa intacta** antes de declarar mejoras. Las predicciones actuales son una señal textual experimental, no comprobación factual.
