# Tarjeta del nuevo mBERT experimental

**Modelo:** `google-bert/bert-base-multilingual-cased`, clasificación binaria `0=REAL, 1=FALSA`. **Estado:** investigación; no validado como verificador factual ni para decisiones automáticas sobre noticias individuales.

## Pesos y entrada

- Checkpoint seleccionado por validación: [mBERT principal, 512 tokens, semilla 43](../runs/BILSTM_ES_main_len512_seed43_20261008-175737_516f4097/best_model), SHA-256 de `model.safetensors`: `44490ba53c6639cb3cd106895f4b2a4872b667751ccd1854515f855c032e294f`.
- Tokenizador local mBERT cased: [assets/tokenizer_mbert_cased](../assets/tokenizer_mbert_cased), SHA-256 de `tokenizer.json`: `f4a4d5bf7301717e261fafbe26e1eb967f6ba4cb3ae0ab7a29f4642ec229f386`.
- Entrada de entrenamiento: `texto` español exacto como **una secuencia**. Si el título ya está dentro, no se concatena otra vez. Truncamiento a 512 tokens y umbral de probabilidad FALSA 0,5. El comando antiguo [inferir_ejemplo.py](../inferir_ejemplo.py) usa el E1 anterior y un par título/cuerpo; no representa este checkpoint.
- [Selección y contrato congelados](../selection/bilstm_step5_20261008_v1/selection.json). Las otras semillas se conservan por separado.

## Datos y entrenamiento

Datos de los CSV BiLSTM auditados, con etiqueta invertida a `0=REAL,1=FALSA`: 2.788 filas de entrenamiento y 132 de validación tras las exclusiones. Entrenamiento principal de tres épocas desde el checkpoint base, `2e-5`, decaimiento 0,01, calentamiento 10 %, lote efectivo 16, BF16. El brazo independiente sin USMSC/Edds y todas las longitudes se documentan en [resultados del paso 4](../PASO_4_RESULTADOS_BILSTM.md). No se usó prueba ni externa para elegir el candidato.

## Rendimiento observado

| Conjunto | F1 macro | FP: REAL→FALSA | FN: FALSA→REAL | Alcance |
|---|---:|---:|---:|---|
| Validación (132) | 0,9385 | 2/89 | 5/43 | Selección; no estimación independiente |
| Prueba BiLSTM filtrada (146) | 0,8976 | 0/110 | 10/36 | Retrospectiva; sesgo de fuente |
| Externa BiLSTM filtrada (569) | 0,6001 | 150/307 | 77/262 | Retrospectiva; alto error práctico |

La matriz, precisión/recall/F1 de cada clase, AP, Brier, predicciones por ID, diferencias con E1 y desglose están en el [informe del paso 6](../evaluations/bilstm_step6_20261008_v1/REPORTE_PASO_6.md). El subconjunto sin exposición conocida de E1 sigue siendo retrospectivo y el de prueba contiene solo Polyglot.

## Limitaciones y uso previsto

Las fuentes, longitudes y etiquetas no son homogéneas: USMSC/Edds aporta textos muy breves al entrenamiento; validación contiene solo dos corpus; múltiples dominios aportan una sola clase; parte de la evaluación ya se había observado en experimentos anteriores. Un puntaje alto puede reflejar estilo, fuente o construcción del corpus y no la verdad de un hecho. La Brier externa es 0,3456, por lo que las probabilidades no están demostradas como calibradas. La prueba final española inédita, con eventos independientes y evidencia de etiquetas, está pendiente según el [protocolo del paso 7](PROTOCOLO_PRUEBA_FINAL.md).

Uso adecuado: investigación, análisis de errores y comparación controlada de corpus. Para una noticia concreta, contrastar hechos con fuentes primarias y verificadores; no usar la salida del clasificador como veredicto.
