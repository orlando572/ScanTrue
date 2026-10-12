# Paso 3: preparación y líneas base del nuevo mBERT

**Fecha:** 8 de octubre de 2026. **Estado:** completo. Todavía no se ha entrenado ningún mBERT nuevo.

## Entradas y salida procesada

Se aplicó la política v4 del paso 2 a los CSV congelados del BiLSTM. [El manifiesto del conjunto procesado](../datasets/processed/mbert_bilstm_step3_20261008_v1/manifest.json) registra hashes de CSV, IDs, política, código y cada archivo de salida. Los archivos son JSONL comprimidos, separados por partición. `text` es una copia exacta de `texto`; `label = 1 - etiqueta` produce `0=REAL, 1=FALSA`. El título ya está dentro de `texto` cuando existe. URL, dataset, título y procedencia quedan como metadatos de auditoría, fuera de la entrada del clasificador. Se verificó la unicidad de IDs entre las cuatro particiones y los conteos de la política v4.

| Partición | Filas | REAL (0) | FALSA (1) |
|---|---:|---:|---:|
| Entrenamiento | 2.788 | 1.756 | 1.032 |
| Validación | 132 | 89 | 43 |
| Prueba | 146 | 110 | 36 |
| Externa | 569 | 307 | 262 |

Los conteos 3.066/170/179/606 del plan corresponden a los CSV **antes** de las exclusiones de calidad y posibles fugas. Los archivos originales y los resultados anteriores no se modificaron.

## Tokenización y truncamiento

El [reporte de tokenización](../datasets/processed/mbert_bilstm_step3_20261008_v1/token_audit.json) se obtuvo con el tokenizador mBERT local, cuya huella SHA-256 coincide con la del paso 1. Se midieron únicamente entrenamiento y validación. Cada ejemplo se codificó como **una secuencia** `[CLS] texto [SEP]`; se inspeccionó un ejemplo decodificado por clase y fuente en cada partición. En los ejemplos con título disponible, el título aparece al inicio de `texto`, de modo que no debe añadirse otra vez.

| Partición | Mediana de subpalabras | >128 | >192 | >256 | >512 |
|---|---:|---:|---:|---:|---:|
| Entrenamiento (2.788) | 70 | 1.111 (39,85 %) | 1.054 (37,80 %) | 1.001 (35,90 %) | 741 (26,58 %) |
| Validación (132) | 629 | 128 (96,97 %) | 118 (89,39 %) | 114 (86,36 %) | 77 (58,33 %) |

La diferencia procede en gran parte de **USMSC/Edds residual**, que aporta 1.647 ejemplos cortos solo al entrenamiento: medianas 62 tokens REAL y 65 FALSA. En cambio, los artículos de las otras fuentes suelen superar 256 tokens. Por ello, la selección en validación mide artículos largos y puede no representar textos breves reales. La ablación de entrenamiento sin USMSC/Edds del paso 4 es obligatoria. El barrido predefinido de 128, 192, 256 y, si cabe en memoria, 512 sigue justificado; las longitudes mayores conservan más cuerpo, pero 512 también trunca 58,33 % de validación.

Una fila de entrenamiento de `spanish_fake_news_corpus_v1` contiene el carácter de sustitución `�` ya presente en el CSV de origen; no se corrigió sin una fuente fiable. No se encontró ese carácter en las otras particiones. Transformers 5.19.0 emitió una advertencia sobre una expresión regular de Mistral al cargar el tokenizador local; la inspección del objeto cargado confirmó `BertTokenizer`, `BertPreTokenizer` y `WordPiece`. No se aplicó el arreglo de Mistral a este tokenizador BERT. La instalación de Python sigue mostrando `Failed to find real location of C:\Python314\python.exe`, aunque los scripts terminaron correctamente.

El comando de inferencia E1 actual usa un par `titulo, cuerpo` cuando hay título. **No sirve como contrato de entrada del nuevo modelo**: en el paso 6 se deberá crear uno que use el mismo `text` como secuencia única, con la longitud del checkpoint seleccionado, sin normalización adicional y con umbral declarado.

## Líneas base, exclusivamente entrenamiento y validación

Se ajustó la clase mayoritaria y dos variantes TF-IDF + regresión logística (`C=1`, umbral 0,5, semilla 42) **solo con los 2.788 ejemplos de entrenamiento**. Se evaluaron en las 132 filas de validación. Los scripts de las líneas base no leen `prueba` ni `externa`. Cada variante se guardó en una carpeta nueva; [el resumen y las rutas](../datasets/processed/mbert_bilstm_step3_20261008_v1/baselines_validation.json) incluyen los artefactos y métricas.

| Línea base | F1 macro | Exactitud | Exactitud balanceada | Reales marcadas falsas | Falsas detectadas |
|---|---:|---:|---:|---:|---:|
| Clase mayoritaria REAL | 0,4027 | 0,6742 | 0,5000 | 0/89 | 0/43 |
| TF-IDF palabras 1–2 | 0,7900 | 0,8409 | 0,7618 | 1/89 | 23/43 |
| TF-IDF caracteres 3–5 | **0,8362** | **0,8712** | **0,8083** | 1/89 | 27/43 |

La variante de caracteres se elige como referencia por F1 macro de validación. Es una referencia de clasificación de estos datos, no una prueba externa de detección factual. La validación es pequeña y procede de solo dos fuentes. Los archivos de prueba y externa ya fueron preparados y sellados por hash, pero **no se tokenizaron, puntuaron ni usaron para elegir ajustes** en este paso.

## Archivos de ejecución

- [Preparación](step3_prepare_bilstm.py)
- [Auditoría de tokens](step3_audit_tokens_bilstm.py)
- [Líneas base](step3_baselines_bilstm.py)

El paso 4 debe cargar estas particiones con verificación de hashes, iniciar cada mBERT desde el checkpoint base y crear una carpeta exclusiva por longitud, semilla y brazo con o sin USMSC/Edds.
