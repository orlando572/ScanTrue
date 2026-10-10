# Paso 6: comparación pareada del mBERT anterior y el nuevo

**Fecha:** 8 de octubre de 2026. **Estado:** evaluación retrospectiva completa; ninguno de los resultados constituye una prueba final inédita ni valida el clasificador para uso real.

Se puntuaron **los mismos IDs y las mismas etiquetas** con el antiguo E1 y las tres semillas de la configuración nueva `main/512`. El candidato semilla 43, umbral 0,5, quedó [congelado en el paso 5](../../selection/bilstm_step5_20261008_v1/selection.json) antes de abrir estas particiones. Se verificaron hashes de datos, tokenizador, modelos y el orden de logits `0=REAL, 1=FALSA`. [El protocolo exacto](protocol.json), [las métricas completas](results.json), [las predicciones por ID](predictions.csv.gz) y [los pares E1–candidato](paired_selected.csv.gz) permiten reproducir la comparación. Ningún modelo ni umbral se modificó después de verla.

El nuevo mBERT recibe `texto` completo como una sola secuencia, máximo **512** tokens. E1 recibe `titulo` y cuerpo como par, máximo **256**. Los CSV BiLSTM no contienen columna `cuerpo`: en las filas donde `texto` empieza con `titulo`, se quitó ese prefijo y se pasó el resto como cuerpo; si no hay título, se pasó `texto` solo. En dos filas externas cuyo título no aparece al inicio se pasó el título junto al texto completo. Son formatos de sistema diferentes; la diferencia observada **no puede atribuirse solo a los datasets**.

## Comparación en todas las filas filtradas

Matriz: filas verdaderas y columnas predichas en orden `REAL, FALSA`. FP = reales marcadas falsas; FN = falsas marcadas reales. AP y Brier corresponden a la probabilidad de FALSA.

| Conjunto | Modelo | N (REAL/FALSA) | F1 macro | Exactitud | Exactitud balanceada | FP | FN | AP | Brier | Matriz |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Prueba | E1 anterior | 146 (110/36) | 0,2325 | 0,2671 | 0,5043 | 106 | 1 | 0,2374 | 0,4636 | `[[4,106],[1,35]]` |
| Prueba | **Nuevo, semilla 43** | 146 (110/36) | **0,8976** | **0,9315** | **0,8611** | **0** | 10 | **0,9658** | **0,0555** | `[[110,0],[10,26]]` |
| Externa | E1 anterior | 569 (307/262) | 0,3191 | 0,4569 | 0,4956 | 305 | 4 | 0,5309 | 0,3678 | `[[2,305],[4,258]]` |
| Externa | **Nuevo, semilla 43** | 569 (307/262) | **0,6001** | **0,6011** | **0,6088** | **150** | 77 | **0,6555** | **0,3456** | `[[157,150],[77,185]]` |

| Conjunto | Modelo | REAL precisión / recall / F1 | FALSA precisión / recall / F1 | Tasa de reales marcadas falsas |
|---|---|---:|---:|---:|
| Prueba | E1 | 0,800 / 0,036 / 0,070 | 0,248 / 0,972 / 0,395 | 96,36 % |
| Prueba | Nuevo 43 | 0,917 / 1,000 / 0,957 | 1,000 / 0,722 / 0,839 | 0,00 % |
| Externa | E1 | 0,333 / 0,007 / 0,013 | 0,458 / 0,985 / 0,625 | 99,35 % |
| Externa | Nuevo 43 | 0,671 / 0,511 / 0,580 | 0,552 / 0,706 / 0,620 | 48,86 % |

La mejora en F1 macro es clara en estas filas, especialmente porque E1 predice FALSA para casi todas las reales. **El nuevo modelo sigue fallando mucho en externa:** 150 falsas alarmas entre 307 reales y 77 falsas no detectadas entre 262. Su F1 de la clase FALSA en externa (0,620) es incluso ligeramente inferior al de E1 (0,625); la mejora en F1 macro procede del gran aumento de reconocimiento de REAL. La Brier externa sigue alta (0,346), así que las probabilidades no deben interpretarse como riesgo calibrado.

En la comparación por ID, ambos modelos discrepan en **117/146** filas de prueba: el nuevo acierta en exclusiva 107 y E1 en exclusiva 10. En externa discrepan en **234/569**: 158 aciertos exclusivos del nuevo y 76 de E1. [El archivo pareado](paired_selected.csv.gz) identifica esos casos sin copiar el texto completo.

## Subconjunto sin exposición conocida al entrenamiento o validación de E1

La [auditoría del paso 2](../../../datasets/processed/mbert_bilstm_step2_20261008_v1/REPORTE_PASO_2.md) detectó coincidencias en **64/146** casos de prueba y **6/569** externos con entrenamiento o validación del antiguo mBERT. Se retiraron esas filas **solo para este análisis adicional**, de forma idéntica para ambos modelos; no se reentrenó ni seleccionó nada con ellas.

| Conjunto común | Modelo | N (REAL/FALSA) | F1 macro | FP | FN | AP | Brier | Matriz |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Prueba sin exposición conocida | E1 | 82 (58/24) | 0,2378 | 57 | 1 | 0,2423 | 0,4519 | `[[1,57],[1,23]]` |
| Prueba sin exposición conocida | Nuevo 43 | 82 (58/24) | **0,9379** | 0 | 4 | 0,9916 | 0,0361 | `[[58,0],[4,20]]` |
| Externa sin exposición conocida | E1 | 563 (306/257) | 0,3172 | 304 | 4 | 0,5264 | 0,3704 | `[[2,304],[4,253]]` |
| Externa sin exposición conocida | Nuevo 43 | 563 (306/257) | **0,5995** | 150 | 75 | 0,6534 | 0,3456 | `[[156,150],[75,182]]` |

Las **82 filas de prueba** de este subconjunto son *todas Polyglot*; no representan una mezcla de fuentes. “Sin exposición conocida” significa que no se halló coincidencia exacta/léxica con entrenamiento o validación de E1; no demuestra independencia de eventos o redacciones. Buena parte de externa ya figuró en las pruebas observadas de la fase F anterior. Ambos análisis son retrospectivos.

## Variación entre semillas y fuentes

| Nueva semilla, 512 tokens | Prueba: F1 macro / FP / FN | Externa: F1 macro / FP / FN |
|---:|---:|---:|
| 42 | 0,9361 / 4 / 3 | 0,5735 / 177 / 62 |
| **43, elegida por validación** | 0,8976 / 0 / 10 | **0,6001** / 150 / 77 |
| 44 | 0,9336 / 2 / 5 | 0,5627 / 184 / 60 |

La semilla 43 no es la mejor en la prueba de 146 filas; se conserva porque fue elegida antes por validación. En externa, las tres semillas quedan entre **0,5627 y 0,6001** de F1 macro. Esa variación impide tomar el número más favorable de cada conjunto como rendimiento del sistema.

El [desglose por fuente y longitud](subgroups.json) muestra que en `fakedes_iberlef_2021` (533 filas) el nuevo obtiene F1 macro **0,6019** con 143 FP y 68 FN; en `falledesinfo_es` (33) obtiene **0,4762** con 7 FP y 8 FN. En externa, el F1 macro del nuevo baja de **0,7178** para textos de menos de 200 palabras a **0,4141** para textos de al menos 1.000 palabras; las bandas tienen distinta composición de clases, por lo que esta asociación no prueba que la longitud sea la causa. En la prueba de 146, las 82 Polyglot obtienen 0,9379 y las 64 Posadas 0,8061, con distinta exposición conocida de E1.

Un [bootstrap pareado por dominio de URL](paired_bootstrap.json), 1.000 sorteos con semilla 42, dio para la diferencia de F1 macro **nuevo − E1** intervalos percentiles descriptivos del 95 %: prueba completa **[0,409, 0,810]**; externa completa **[0,230, 0,320]**; subconjunto externo sin exposición conocida **[0,235, 0,324]**. El intervalo del subconjunto de prueba fue **[0,636, 0,863]**, pero solo 657 de 1.000 sorteos conservaron ambas clases y sus 82 filas son de una fuente; debe interpretarse con especial cautela. Los dominios no equivalen necesariamente a eventos independientes ni corrigen las etiquetas dudosas o la exposición previa del investigador.

## Conclusión y límite práctico

El nuevo entrenamiento reduce de forma importante el sesgo del E1 hacia FALSA y mejora el F1 macro en estas dos comparaciones pareadas. **Todavía no es un verificador fiable de noticias individuales**: en externa casi la mitad de las noticias reales reciben una falsa alarma y cerca del 29 % de las falsas no se detectan. Además, los dos conjuntos disponibles son retrospectivos y tienen sesgo de fuente y posibles eventos relacionados. El paso 7 requiere una prueba española inédita, congelada antes de puntuar, para evaluar la mejora fuera de estos datos ya observados.
