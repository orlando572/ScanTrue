# Resultados y pruebas del mBERT de producción

> **Archivado el 11 nov 2026:** la app usa ahora BETO M3b ([RESULTADOS_MODELO_NUEVO.md](RESULTADOS_MODELO_NUEVO.md)); este modelo se conserva sin uso en `datasets/mbert_produccion/archivo_octubre/`.

Fue el mBERT de la app hasta el 11 nov 2026: `google-bert/bert-base-multilingual-cased` (revisión `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`) ajustado como clasificador binario, configuración `main/512`, semilla 43, corrida `BILSTM_ES_main_len512_seed43_20261008-175737_516f4097`. Se entrenó el 8 de octubre de 2026.

> Los scripts que lo prepararon, entrenaron, eligieron y evaluaron (`step1_…` a `step7_…`, `train_bilstm_step4.py`, `run_bilstm_step4_matrix.py`, `select_bilstm_step5.py`, `evaluate_bilstm_step6.py`, `inferir_bilstm_mbert.py`…) y los informes originales (`PASO_3`, `PASO_4`, `PLAN_REENTRENAMIENTO_BILSTM_20261008.md`, `REPORTE_PASO_5/6`, `MODELO_NUEVO_TARJETA.md`, `CIERRE_RETROSPECTIVO.md`) se retiraron en la limpieza del 10 nov 2026. Están en el historial de Git (commit `ece259a`). El informe técnico completo sigue en [INFORME_TECNICO.md](INFORME_TECNICO.md).

## Dónde está cada cosa

| Qué | Ruta | En Git |
| --- | --- | --- |
| Pesos (`model.safetensors`, 711 MB), `config.json` y tokenizador copiado | `datasets/mbert_produccion/archivo_octubre/modelo/best_model/` | Sí, pesos con LFS |
| Tokenizador congelado | `datasets/mbert_produccion/archivo_octubre/modelo/tokenizer_mbert_cased/` | Sí |
| Contrato de selección | `datasets/mbert_produccion/archivo_octubre/modelo/selection.json` | Sí |
| Configuración, hashes de datos, log y métricas de la corrida | `datasets/mbert_produccion/archivo_octubre/modelo/{config,data_manifest,metrics_validation}.json`, `train_log.jsonl` | Sí |
| Datos de entrenamiento y evaluación (JSONL) y su auditoría | `datasets/mbert_produccion/conjunto/` | No (textos de terceros) |
| Predicciones y métricas de validación, prueba y externa | `datasets/mbert_produccion/evaluaciones/` | No |

`config.json` y `selection.json` conservan las rutas absolutas de entonces (`D:\ScanTrue\mBERT\runs\…`). El backend ya no usa este modelo.

| Archivo | SHA-256 |
| --- | --- |
| `best_model/model.safetensors` | `44490ba53c6639cb3cd106895f4b2a4872b667751ccd1854515f855c032e294f` |
| `tokenizer_mbert_cased/tokenizer.json` | `f4a4d5bf7301717e261fafbe26e1eb967f6ba4cb3ae0ab7a29f4642ec229f386` |

## Datos utilizados

Los cuatro CSV del BiLSTM de entonces (`modelo bilstm/`), con la política de exclusiones v4: se quitaron cinco dominios de sátira, las publicaciones de redes sociales y 38 filas de entrenamiento casi duplicadas de las pruebas. La etiqueta se invirtió a **`0=REAL`, `1=FALSA`** (`label = 1 − etiqueta_bilstm`), la misma convención que `etiqueta_falsa` del conjunto común. La entrada fue solo `texto` (con el titular dentro cuando existía), como una secuencia `[CLS] texto [SEP]`.

| Partición | Filas | Reales | Falsas | Fuentes |
| --- | ---: | ---: | ---: | --- |
| Entrenamiento | 2.788 | 1.756 | 1.032 | v1 (527), Polyglot (614), USMSC/Edds residual (1.647) |
| Validación | 132 | 89 | 43 | v1 (61), Polyglot (71) |
| Prueba | 146 | 110 | 36 | Polyglot (82), Posadas (64) |
| Externa | 569 | 307 | 262 | FakeDeS (533), FalleDesinfo (33)… |

Los hashes de `entrenamiento.jsonl.gz` (`46a01be6…`) y `validacion.jsonl.gz` (`8ef8d0ca…`) coinciden con `modelo/data_manifest.json`.

**Desajuste de longitudes:** la mediana de subpalabras era **70** en entrenamiento (por los 1.647 fragmentos USMSC de unas 300 letras) y **629** en validación. A 512 tokens se truncaba el 58 % de la validación.

## Entrenamiento y selección

24 corridas independientes desde el modelo base: 2 brazos (`main`, `no_usmsc`) × 4 longitudes × 3 semillas. Receta común: 3 épocas, lr `2e-5`, decaimiento 0,01, calentamiento 10 %, lote efectivo 16, BF16, RTX 5060 de 8 GB. Mejor época por F1 macro de validación (empate a favor de la anterior).

| Brazo | Tokens | F1 macro validación (media ± DE, 3 semillas) | Falsas alarmas | Tiempo medio |
| --- | ---: | ---: | ---: | ---: |
| main | 128 | 0,8829 ± 0,0127 | 8,2 % | 162 s |
| main | 192 | 0,8921 ± 0,0212 | 8,2 % | 163 s |
| main | 256 | 0,9117 ± 0,0134 | 6,7 % | 163 s |
| **main** | **512** | **0,9220 ± 0,0143** | **4,5 %** | 445 s |
| no_usmsc | 128 | 0,8596 ± 0,0157 | 11,6 % | 80 s |
| no_usmsc | 192 | 0,8761 ± 0,0054 | 7,9 % | 67 s |
| no_usmsc | 256 | 0,8907 ± 0,0128 | 7,1 % | 60 s |
| no_usmsc | 512 | 0,8985 ± 0,0270 | 5,2 % | 131 s |

Regla: mayor media de F1 macro; si la diferencia era menor de 0,01, menos falsas alarmas y después menor longitud. `main/512` ganó a `main/256` por **0,0103**, apenas por encima del margen. Dentro de `main/512` se tomó la semilla con mejor validación, la **43** (0,9385; las otras, 0,9127 y 0,9148). Umbral de falsa 0,5, sin calibración.

Referencia de entonces en la misma validación: TF-IDF de caracteres 3–5 + regresión logística, F1 macro **0,8362**.

## Métricas registradas

Matrices en orden `[real, falsa]` (filas = etiqueta real, columnas = predicción).

| Evaluación | F1 macro | Reales marcadas falsas | Falsas no detectadas | Brier | Matriz |
| --- | ---: | ---: | ---: | ---: | --- |
| Validación (132) | 0,9385 | 2 de 89 | 5 de 43 | — | `[[87, 2], [5, 38]]` |
| Prueba (146) | 0,8976 | 0 de 110 | 10 de 36 | 0,056 | `[[110, 0], [10, 26]]` |
| Externa (569) | **0,6001** | **150 de 307 (48,9 %)** | 77 de 262 | **0,346** | `[[157, 150], [77, 185]]` |

- **Variación entre semillas (externa):** 0,5735 (s42), 0,6001 (s43), 0,5627 (s44). La semilla 43 ganó en validación y fue la peor de las tres en prueba (0,898 frente a 0,936 y 0,934).
- **Por fuente (externa):** FakeDeS 0,6019; FalleDesinfo 0,4762.
- **Por longitud (externa):** 0,7178 en textos de menos de 200 palabras y 0,4141 en los de 1.000 o más.
- **Frente al mBERT anterior (E1, 256 tokens, título y cuerpo como par):** 0,2325 → 0,8976 en prueba y 0,3191 → 0,6001 en externa. E1 marcaba como falsas casi todas las reales.

## Límites

- **La validación no predijo la externa** (0,939 → 0,600). Con 132 filas de dos fuentes, un error movía el F1 en 0,008: la elección de longitud y semilla fue en buena parte ruido.
- **Atajos:** casi cada dominio aporta una sola clase (100 % en Polyglot) y las falsas son más cortas. Un clasificador que solo cuenta palabras saca 0,663 en la externa, más que este modelo.
- **Probabilidades sin calibrar:** Brier externo 0,346, peor que responder siempre 0,5 (0,25).
- **Solo se guardaron clases en validación** (`predictions_validation.jsonl` tiene `pred`, no probabilidades): no sirven para calibrar ni combinar.
- **Pruebas retrospectivas:** prueba y externa ya se habían observado en fases anteriores. La prueba inédita del paso 7 no se llegó a ejecutar por falta de un conjunto apto.

Todo esto motivó el plan nuevo ([03_PLAN_MBERT.md](../../docs/mejora_modelos/03_PLAN_MBERT.md)): conjunto común `comun_v1`, validación dejando una fuente fuera y predicciones con logits. Los resultados nuevos van en [RESULTADOS_MODELO_NUEVO.md](RESULTADOS_MODELO_NUEVO.md).

## Cómo lo usa la app

[`backend/models/mbert.py`](../../backend/models/mbert.py) lee `selection.json`, exige `max_length == 512` y etiquetas `{"REAL": 0, "FALSA": 1}`, verifica el SHA-256 del tokenizador y de los pesos, recorta el texto a 512 tokens por offsets y devuelve `probabilidad_falsa` (salida 1 del modelo) con umbral 0,5. Con Git LFS instalado, `git lfs pull` descarga los pesos; sin LFS, `model.safetensors` es un puntero de 3 líneas y el backend no carga mBERT.
