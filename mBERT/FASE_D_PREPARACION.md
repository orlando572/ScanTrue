# Fase D — preparación para mBERT y líneas base

**Fecha:** 7 de octubre de 2026. **Estado:** completada y verificada. No se ha ajustado mBERT ni se han calculado métricas en las pruebas reservadas.

## Datos preparados

Se comprobaron el hash de fase B y los 48 772 IDs/decisiones de fase C antes de preparar los textos. Los siete archivos `*.jsonl.gz` de [phase_d_mbert_20261007_v1](../datasets/processed/phase_d_mbert_20261007_v1) corresponden exactamente a las particiones activas congeladas: 667/289/451 registros españoles de entrenamiento/validación/prueba principal; 750 en prueba española Polyglot; 29 949/7 488 ingleses de entrenamiento/validación; y 949 en prueba inglesa Pérez-Rosas. El [manifiesto](../datasets/processed/phase_d_mbert_20261007_v1/manifest.json) conserva hashes de cada archivo y del origen; la [verificación](../datasets/processed/phase_d_mbert_20261007_v1/verification.json) confirmó IDs, etiquetas, tamaño de cada partición y lotes tokenizados con las cuatro longitudes.

Cada registro preparado tiene ID, partición, etiqueta, idioma, corpus, titular, cuerpo y `input_mode`. Ni fuente ni URL se incluyen como entrada del modelo. En ISOT se retiró la dateline inicial `Ciudad (Reuters) -` de los cuerpos en los casos donde aparecía; el conteo por partición está en el manifiesto. Es una mitigación parcial del sesgo de fuente, no lo elimina. Los tres ejemplos de la prueba principal sin titular usan **solo cuerpo**. Para una ablación «solo titular», esos tres se excluirán de ambos brazos de la comparación, conservando los mismos IDs en cada brazo.

El tokenizador oficial de [`google-bert/bert-base-multilingual-cased`](https://huggingface.co/google-bert/bert-base-multilingual-cased/tree/main) se descargó sin pesos del modelo, fijado al commit `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`, en [tokenizer_mbert_cased](assets/tokenizer_mbert_cased). Es cased y tiene máximo de 512 posiciones. La función reutilizable [phase_d_data.py](phase_d_data.py) carga archivos con verificación SHA-256 y produce `Dataset` tokenizados y `DataCollatorWithPadding` para 128, 192, 256 o 512. La entrada principal es `tokenizer(titular, cuerpo, truncation="only_second", max_length=L)`, equivalente a `[CLS] titular [SEP] cuerpo [SEP]`; se conserva el titular y se trunca el cuerpo. El padding es dinámico por lote. [Documentación de truncamiento](https://huggingface.co/docs/transformers/main/pad_truncation).

Transformers 5.19.0 emite una advertencia sobre `fix_mistral_regex` al cargar este tokenizador BERT local. Se comprobó que el vocabulario cargado tiene 119 547 entradas y que la tokenización funciona. **No se aplicó** `fix_mistral_regex=True`: cambia la segmentación de BERT para una cadena de prueba (`19` pasa de un token a dos). Hay [incidencias conocidas en Transformers para tokenizadores no Mistral](https://github.com/huggingface/transformers/issues/42591). El proceso de preparación y las cuatro pruebas de tokenización terminaron correctamente.

## Longitudes observadas

Solo se inspeccionaron entrenamiento y validación para decidir configuración; las pruebas quedaron cerradas. Los porcentajes indican artículos cuyo titular+cuerpo excede la longitud y perdería parte del cuerpo. Son **tokens reales del tokenizador mBERT**, incluidos tokens especiales.

| Partición | Mediana de tokens | >128 | >192 | >256 | >512 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `es_train` | 494 | 99,70 % | 97,45 % | 91,00 % | 47,08 % |
| `es_validation` | 513 | 99,31 % | 96,89 % | 93,08 % | 50,17 % |
| `en_train` | 519 | 92,16 % | 84,87 % | 80,77 % | 51,10 % |
| `en_validation` | 515 | 92,19 % | 85,31 % | 80,93 % | 50,37 % |

Estos datos justifican mantener experimentos independientes para **128, 192 y 256**; 512 es especialmente informativo si cabe en los 8 GB de VRAM con un lote menor. La longitud que maximice F1 debe elegirse con validación española, atendiendo también precisión/recall y coste. La pérdida de texto no demuestra por sí sola que 512 vaya a mejorar.

## Líneas base E0

Se ajustaron modelos independientes `TF-IDF` (palabras, unigramas y bigramas, hasta 100 000 rasgos) + regresión logística con umbral fijo 0,5. Cada uno tiene **su propia carpeta**, modelo guardado, hashes de los IDs y métricas de validación. Como referencia también se calculó el predictor de clase mayoritaria. Ninguna línea base usó pruebas ni cuarentena.

| Ejecución | Entrena con | Valida con | F1 FALSA mayoría | F1 FALSA TF-IDF | Precisión TF-IDF | Recall TF-IDF | F1 macro TF-IDF |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| [E0 español](runs/E0_es_seed42_phaseD_v1/metrics_validation.json) | `es_train` | `es_validation` | 0,000 | 0,775 | 0,795 | 0,755 | 0,788 |
| [E0 inglés](runs/E0_en_seed42_phaseD_v1/metrics_validation.json) | `en_train` | `en_validation` | 0,000 | 0,984 | 0,991 | 0,977 | 0,986 |
| [E0 mixto](runs/E0_mixed_seed42_phaseD_v1/metrics_validation.json) | `es_train` + `en_train` | `es_validation` | 0,000 | 0,769 | 0,761 | 0,777 | 0,775 |

El F1 interno inglés muy alto es consistente con el riesgo de atajos de fuente de ISOT y **no** anticipa la prueba española. En esta línea base lineal, añadir inglés no mejoró el F1 español de validación frente a entrenar solo con español; esto no decide el resultado de mBERT. Las métricas completas, incluida matriz de confusión y average precision, están en cada ejecución.

## Siguiente paso 

La fase E puede iniciar modelos mBERT desde el checkpoint oficial, con cada combinación de experimento/longitud/semilla en una **carpeta exclusiva**. Deberá usar los archivos y hashes de este manifiesto, verificar la API instalada de Transformers, vigilar memoria de GPU y seleccionar modelos solo con las validaciones. El checkpoint de pesos aún no se descargó; se descargará al comenzar E. Persisten las limitaciones de las fases anteriores: sesgos de fuente, prueba Polyglot solo de estrés y posible solapamiento semántico no detectado automáticamente.
