# Paso 5: selección del nuevo mBERT mediante validación

**Fecha:** 8 de octubre de 2026. **Estado:** candidato congelado para el paso 6. Se utilizaron únicamente las métricas y predicciones de los 132 ejemplos de validación; no se abrieron prueba ni externa. La decisión reproducible y los hashes están en [selection.json](selection.json).

## Regla aplicada

Se comparó la **media de F1 macro de tres semillas** por configuración (brazo y longitud). El plan fijaba que, si la diferencia frente a la mejor media fuese estrictamente menor de **0,01**, ganaría la configuración con menor tasa media de reales marcados falsos; después, la más corta. La mejor media fue `main/512`: **0,921988**. La siguiente fue `main/256`: **0,911655**. La diferencia exacta, **0,010334**, supera por poco el margen de empate; por eso ganó `main/512` por F1 macro. Esta decisión es sensible al margen fijado y se informará como tal.

| Configuración | F1 macro media ± DE | Tasa media de reales marcados falsos |
|---|---:|---:|
| Principal, 256 tokens | 0,9117 ± 0,0134 | 6,74 % |
| **Principal, 512 tokens** | **0,9220 ± 0,0143** | **4,49 %** |
| Sin USMSC/Edds, 512 tokens | 0,8985 ± 0,0270 | 5,24 % |

Las ocho configuraciones y las 24 corridas constan en [PASO_4_RESUMEN.json](../../PASO_4_RESUMEN.json). Dentro de `main/512`, la semilla **43** tuvo la mayor F1 macro (0,938494), frente a 0,912698 para la 42 y 0,914773 para la 44. Se conserva la información de las tres para la comparación de variación del paso 6.

## Checkpoint elegido

- [Modelo semilla 43](../../runs/BILSTM_ES_main_len512_seed43_20261008-175737_516f4097/best_model) (`model.safetensors` SHA-256 `44490ba53c6639cb3cd106895f4b2a4872b667751ccd1854515f855c032e294f`).
- Longitud máxima **512**, secuencia única `text` exacta, truncamiento al final, tokenizador local de [assets/tokenizer_mbert_cased](../../assets/tokenizer_mbert_cased); no añadir `titulo` otra vez ni normalizar el texto.
- Etiquetas `0=REAL`, `1=FALSA`. Umbral de probabilidad `FALSA` **0,5**, sin calibración ni variante de umbral.
- El tokenizador copiado al directorio del modelo tiene un hash de archivo distinto por serialización, pero generó **los mismos IDs en los 132 textos de validación**. Para el paso 6 se fija expresamente el tokenizador original de `assets` y su SHA-256 en `selection.json`.

## Validación del checkpoint elegido

| Clase | Soporte | Precisión | Recall | F1 |
|---|---:|---:|---:|---:|
| REAL | 89 | 0,9457 | 0,9775 | 0,9613 |
| FALSA | 43 | 0,9500 | 0,8837 | 0,9157 |

F1 macro **0,9385**; exactitud **0,9470**; exactitud balanceada **0,9306**. Matriz de confusión con filas verdaderas y columnas predichas en orden `REAL, FALSA`: `[[87, 2], [5, 38]]`. La tasa de falsas alarmas es **2/89 = 2,25 %**. Se recomputó la matriz y F1 a partir de las predicciones por ID y se verificó que coinciden con las métricas guardadas.

El desglose por fuente muestra una limitación de esta validación: `spanish_fake_news_corpus_v1` tiene matriz `[[43, 2], [3, 13]]` (61 casos), mientras que `polyglotfakefacts_v2` tiene `[[44, 0], [2, 25]]` (71 casos). La clase FALSA es más difícil en la primera fuente (recall 13/16 frente a 25/27). Solo hay dos fuentes en validación y 43 noticias falsas en total; la estimación puede variar con otros medios y eventos.

## Estado de la comparación

El antiguo E1 queda identificado por su checkpoint y hash en [selection.json](selection.json), con su entrada `titulo, cuerpo` y longitud 256. **Aún no se ha puntuado ninguno de los dos modelos sobre las mismas noticias de prueba o externa.** Esa comparación pareada, con las tres semillas de la configuración elegida y los subconjuntos de exposición documentados en el paso 2, corresponde al paso 6. Las pruebas disponibles son retrospectivas; una conclusión de superioridad en noticias nuevas requerirá la prueba inédita del paso 7.

## Prueba manual con comando

El [comando de inferencia del nuevo modelo](../../inferir_bilstm_mbert.py) permite introducir el texto completo con `--texto` o `--archivo-texto`. También admite `--titulo` y `--cuerpo` (o `--archivo-cuerpo`) y los combina como una sola secuencia. Verifica los hashes del modelo y tokenizador congelados al cargar. La salida es una clasificación textual experimental y las probabilidades todavía no están calibradas; no constituye comprobación factual de una noticia. La evaluación pareada del paso 6 sigue pendiente.
