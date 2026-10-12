# Plan de nuevo entrenamiento mBERT con las particiones del BiLSTM

**Fecha:** 8 de octubre de 2026. **Estado:** pasos 1–6 completados; paso 7 preparado y cerrado provisionalmente sin prueba inédita por falta de un conjunto apto. El [manifiesto y reporte del paso 1](../datasets/processed/mbert_bilstm_step1_20261008_v1/REPORTE_CALIDAD.md), el [reporte del paso 2](../datasets/processed/mbert_bilstm_step2_20261008_v1/REPORTE_PASO_2.md), el [reporte del paso 3](PASO_3_PREPARACION_BILSTM.md), los [resultados del paso 4](PASO_4_RESULTADOS_BILSTM.md), la [selección del paso 5](selection/bilstm_step5_20261008_v1/REPORTE_PASO_5.md), la [comparación del paso 6](evaluations/bilstm_step6_20261008_v1/REPORTE_PASO_6.md) y el [cierre provisional](final_test_step7/CIERRE_RETROSPECTIVO.md) registran el trabajo ejecutado. Este plan complementa [PLAN_ENTRENAMIENTO.md](PLAN_ENTRENAMIENTO.md) y no altera los resultados de las fases A–F.

## Objetivo y reglas fijas

Entrenar una **nueva familia de checkpoints** `google-bert/bert-base-multilingual-cased` con los CSV de `modelo bilstm`, en español, y comparar el candidato resultante con el **mBERT inicial E1, longitud 256, semilla 44** sobre los mismos ejemplos. Las comparaciones usarán `0=REAL, 1=FALSA`, la codificación del mBERT existente. La etiqueta de los CSV BiLSTM es inversa (`0=FALSA, 1=REAL`), por lo que la conversión será `label_mbert = 1 - etiqueta_bilstm`, con verificaciones por clase y ejemplos conocidos.

Cada entrenamiento empezará de una **copia leída del checkpoint base oficial**, nunca de E1 ni de otro entrenamiento de este plan. Cada longitud y semilla tendrá una carpeta nueva e inmutable. Se mantendrán los modelos, datos y evaluaciones anteriores. Ningún resultado del BiLSTM se usará para elegir hiperparámetros mBERT.

La entrada principal será **solo `texto`**. Ya incorpora el titular cuando existe; concatenar `titulo` duplicaría contenido. El tokenizador mBERT no usa la columna `tokens` del BiLSTM. El texto se conservará con tildes, mayúsculas y puntuación; `dataset`, `url`, `origen` y `etiqueta` servirán para auditoría, nunca como entrada. No se añadirán datasets ingleses en el experimento principal: la pregunta de este ciclo es el efecto de los **nuevos datos españoles**, sin cambiar a la vez el idioma de entrenamiento.

## Paso 1. Congelar entradas y registrar procedencia

1. Copiar o referenciar como entrada inmutable `entrenamiento.csv` (3.066), `validacion.csv` (170), `prueba.csv` (179) y `externa.csv` (606); registrar SHA-256, columnas, recuentos de clase y origen. Guardar un manifiesto nuevo bajo `datasets/processed/` sin sustituir el de la fase D.
2. Registrar la revisión exacta del modelo/tokenizador base, versiones efectivas de Python, PyTorch, CUDA y Transformers, GPU, semilla y código usado. Reutilizar los activos locales de `mBERT/assets` tras comprobar su hash.
3. Documentar las limitaciones de procedencia: 1.683 residuales USMSC/Edds sin titular ni URL; 54,9 % del entrenamiento y ausentes de validación/prueba. Los scripts originales que produjeron el conjunto BiLSTM no están disponibles aquí. Revisar una muestra estratificada por fuente y clase para detectar etiquetas dudosas, textos de verificación, sátira y titulares duplicados. Registrar cada exclusión o corrección; no editar los CSV originales.
4. Definir antes de entrenar el protocolo de comparación y, si se consigue una prueba final inédita, congelar su origen, criterios de inclusión y reglas de exclusión sin consultar predicciones. Si todavía no existe, dejar expresamente pendiente la conclusión final; no sustituirla por una prueba ya observada.

**Salida:** manifiesto de entradas y reporte de calidad. **Puerta:** cero textos/etiquetas vacíos, etiquetas únicamente `0/1`, y correspondencia de hashes con la auditoría actual.

## Paso 2. Auditar particiones y posibles fugas

1. Repetir controles entre entrenamiento, validación, prueba y externa por `id`, URL, texto, título y `grupo_duplicados`; añadir similitud de titulares/cuerpos y revisión de noticias del mismo evento. La auditoría actual no halló cruces exactos, pero no descarta paráfrasis.
2. Cruzar **los cuatro CSV** con las particiones usadas por el mBERT inicial, sobre todo su entrenamiento/validación y pruebas. Conservar una tabla de pares y marcar por separado coincidencias exactas, posibles eventos repetidos y diferencias de etiqueta. Se sabe que 543 textos del entrenamiento BiLSTM coinciden con la antigua prueba de estrés Polyglot; esta última queda descartada como prueba independiente del nuevo modelo.
   Para la comparación en `prueba.csv` y `externa.csv`, identificar por ID, texto y evento las filas que ya estuvieron en el entrenamiento o selección de **cualquiera** de los dos mBERT. Informar resultados en todas las filas como diagnóstico retrospectivo y en un subconjunto común sin exposición conocida, con sus tamaños por clase. Si ese subconjunto es demasiado pequeño o sesgado, no usarlo para afirmar superioridad.
3. Revisar sesgo de fuente y longitud por clase. La auditoría anterior encontró 1.367/1.383 ejemplos con URL de entrenamiento en dominios que aportan una sola clase. Las conclusiones deberán desglosarse por fuente y longitud, no solo por promedio global.
4. Fijar una lista de exclusiones por fuga o etiqueta incompatible **antes de entrenar**. Mantener un experimento principal con los datos auditados y, si la revisión de USMSC/Edds lo justifica, una ablación separada sin esos residuales. Una exclusión no se decidirá por el resultado del modelo.

**Salida:** reporte de cruces y particiones congeladas con IDs y hashes. **Puerta:** ningún grupo conocido del entrenamiento cruza validación o pruebas; cualquier excepción queda documentada y se excluye de las comparaciones afectadas.

**Decisión ejecutada:** la política final está en [policy_v4.json](../datasets/processed/mbert_bilstm_step2_20261008_v1/policy_v4.json): 2.788/132/146/569 filas conservadas. Se excluyeron del brazo principal cinco fuentes declaradas de sátira/ficción, URLs sociales directas y 38 filas de entrenamiento parecidas a pruebas. El brazo sin USMSC/Edds pasa de condicional a **obligatorio** por la diferencia extrema de longitud y procedencia; tendrá 1.141 filas de entrenamiento.

## Paso 3. Preparar entrada mBERT y línea base

1. Crear una versión procesada separada con `id`, `label_mbert`, `texto`, partición y metadatos de auditoría. Verificar explícitamente los conteos originales antes de exclusiones (`1.309 FALSA / 1.757 REAL` en entrenamiento, `81/89` en validación, `69/110` en prueba y `299/307` en externa) y los conteos finales de la política v4 tras las exclusiones y la inversión: entrenamiento `1.032 FALSA / 1.756 REAL`, validación `43/89`, prueba `36/110`, externa `262/307`.
2. Tokenizar `texto` como secuencia única. Medir subpalabras mBERT y truncamiento en **entrenamiento y validación**, para 128, **192**, 256 y 512 tokens. Inspeccionar ejemplos decodificados de ambas clases y fuentes; comprobar que inferencia aplique idéntica normalización, entrada y truncamiento.
3. Ajustar, solo sobre el nuevo entrenamiento, dos referencias: clase mayoritaria y TF-IDF + regresión logística. Elegir cualquier ajuste de la línea base con validación y guardar sus artefactos en rutas nuevas.

**Salida:** datos preparados, informe de truncamiento y métricas de validación de las líneas base. El código `train_phase_e.py` lee el antiguo manifiesto y usa entrada titular/cuerpo; requerirá una implementación o adaptación **con nuevas rutas y comprobaciones**, no una invocación directa sobre estos CSV.

**Ejecución:** completada el 8 de octubre de 2026. La validación tiene 132 ejemplos tras la política v4. El 86,36 % supera 256 tokens y el 58,33 % supera 512; el fuerte contraste de longitudes por fuente exige informar resultados por fuente y ejecutar la ablación sin USMSC/Edds ya fijada. La mejor línea base TF-IDF por validación obtuvo F1 macro 0,8362. Las métricas, rutas y límites se documentan en [PASO_3_PREPARACION_BILSTM.md](PASO_3_PREPARACION_BILSTM.md).

## Paso 4. Entrenamientos independientes

**Barrido inicial predefinido:** 128, 192 y 256 tokens, desde el mismo checkpoint base; tasa inicial `2e-5`, tres épocas, decaimiento `0,01`, calentamiento 10 %, lote efectivo cercano a 16 y precisión mixta si la GPU la admite. Son puntos de partida del entorno anterior, sujetos a comprobarse al ejecutar. Registrar tiempo y pico de VRAM. Probar 512 tokens como experimento independiente si cabe en los 8 GB, con lote menor y acumulación de gradientes; registrar si no cabe.

Para cada longitud viable, usar semillas **42, 43 y 44**. La comparación de longitudes se hará por media y dispersión de validación, no escogiendo una sola semilla afortunada. Si el barrido muestra una razón clara para variar tasa, pesos de clase o muestreo, realizar un segundo bloque **predefinido y separado**, cambiando un factor a la vez. Los pesos o muestras se calculan exclusivamente del entrenamiento. No usar `prueba.csv` ni `externa.csv` para ajustes, umbral, parada o selección.

**Ejecución:** completada el 8 de octubre de 2026. Las cuatro longitudes, incluida 512, resultaron viables en la RTX 5060 Laptop. Se completaron 24 corridas: dos brazos (`main` y `no_usmsc`) × cuatro longitudes × tres semillas, cada una desde el checkpoint base. Se verificaron tres checkpoints por corrida, hashes y recarga del mejor. Las medias y la dispersión de validación están en [PASO_4_RESULTADOS_BILSTM.md](PASO_4_RESULTADOS_BILSTM.md). La selección formal queda para el paso 5.

Cada ejecución tendrá ruta exclusiva, por ejemplo:

```text
mBERT/runs/BILSTM_ES_len192_seed42_YYYYMMDD-HHMMSS_<id>/
  config.json
  data_manifest.json
  train_log.jsonl
  checkpoints/
  best_model/
  metrics_validation.json
```

La creación debe fallar si la carpeta ya existe; no se sobreescriben artefactos. Si falla una ejecución, queda registrada y el reintento obtiene otro ID. Guardar todos los checkpoints por época, configuración, hash de pesos, semilla, duración y memoria. Verificar que el modelo recargado reproduce sus métricas de validación.

## Paso 5. Selección usando solo validación

La **métrica principal de selección** será F1 macro español, porque el modelo anterior logró alto recall de FALSA a costa de marcar demasiadas noticias reales como falsas. Informar siempre F1, precisión y recall de cada clase; tasa de reales marcadas falsas (FP / reales); exactitud balanceada y matriz de confusión. Entre configuraciones cuya media de F1 macro difiera menos de **0,01**, preferir la de menor tasa de falsas alarmas; si persiste el empate, la de menor longitud. Esta regla y el umbral inicial de probabilidad falsa `0,5` se congelarán antes de ver pruebas. La mejor época de cada ejecución se elegirá por F1 macro de validación, con desempate por época más temprana.

Elegir la **configuración** por la media de las tres semillas. Para disponer de un checkpoint concreto, elegir dentro de esa configuración la semilla con mayor F1 macro de validación y registrar también las otras dos. Cualquier calibración o umbral distinto de `0,5` deberá ajustarse solo con validación y declararse como variante aparte; no se optimizará después de abrir pruebas. La validación pequeña (170 casos originales, 132 tras exclusiones) limita la precisión de la selección.

**Ejecución:** completada el 8 de octubre de 2026 con las **132 filas conservadas** tras la política v4. Ganó `main/512` por media de F1 macro **0,9220**; la diferencia exacta con `main/256` es **0,010334**, apenas por encima del margen de empate de 0,01. Dentro de esa configuración se eligió la semilla **43**, F1 macro individual **0,9385**, y se congelaron checkpoint, hashes, tokenizador, entrada y umbral 0,5 en [selection.json](selection/bilstm_step5_20261008_v1/selection.json). No se usaron prueba ni externa. No se realizó calibración.

## Paso 6. Evaluación pareada y comparación con el mBERT inicial

Congelar checkpoint, entrada, longitud y umbral del nuevo candidato. Después evaluar **una vez** el candidato nuevo y el E1 inicial sobre las **mismas filas e IDs** de `prueba.csv` y `externa.csv`, aplicando a cada modelo su formato de entrada documentado y la misma verdad de referencia. Verificar la inversión de etiqueta y el orden `REAL, FALSA` en logits, probabilidades, matriz y salida. Las diferencias de representación son parte de la comparación de sistemas y se declararán; no atribuir por sí solas la diferencia a los datos.

Presentar una tabla pareada por conjunto y por clase: soporte, precisión, recall, F1, F1 macro, exactitud, exactitud balanceada, FP, FN, tasa de falsas alarmas, average precision y Brier. Conservar predicción y probabilidad por ID, sin copiar artículos completos a los reportes; incluir desacuerdos y análisis por fuente/longitud. Cuando corresponda, estimar incertidumbre de la **diferencia pareada** mediante remuestreo por grupo de evento o fuente. Repetir la comparación con las tres semillas de la configuración elegida para mostrar variación.

No mezclar en una misma cifra las filas expuestas previamente a uno de los modelos con las no expuestas. Presentar el análisis de todas las filas y el subconjunto común sin exposición conocida por separado; indicar que la ausencia de coincidencia exacta no prueba independencia semántica.

**Ejecución:** completada el 8 de octubre de 2026. La comparación pareada retrospectiva de E1 frente al nuevo `main/512/seed43` dio F1 macro **0,2325 frente a 0,8976** en las 146 filas de prueba y **0,3191 frente a 0,6001** en las 569 externas. En externa el nuevo todavía produce **150 falsas alarmas entre 307 reales** y 77 falsas no detectadas. Se informan aparte las 82/563 filas sin exposición conocida al entrenamiento o validación de E1, las otras dos semillas, AP, Brier, desglose y bootstrap en [REPORTE_PASO_6.md](evaluations/bilstm_step6_20261008_v1/REPORTE_PASO_6.md). Estos resultados no sustituyen una prueba final inédita.

`prueba.csv` (179) y `externa.csv` (606) tienen límites: el E1 inicial pudo ver durante su entrenamiento ejemplos de Posadas/Polyglot que aparecen en la prueba BiLSTM, lo que se determinará en el paso 2; `externa.csv` ya se consultó para seleccionar variantes BiLSTM. Por ello ambas comparaciones serán **retrospectivas/exploratorias**. Los números antiguos publicados en la fase F proceden de otros ejemplos y no se usarán como comparación directa. La antigua prueba Polyglot tampoco será una prueba válida para el nuevo modelo por el solapamiento conocido.

## Paso 7. Prueba final independiente y cierre

Antes de afirmar que el nuevo mBERT supera al inicial para noticias reales, obtener o construir un **nuevo conjunto español no utilizado en ningún entrenamiento, validación ni selección previa**, con criterio de etiqueta documentado, varios medios por clase y mezcla de temas/longitudes. Auditar derechos de uso, copias y eventos compartidos con todos los datos anteriores. Congelar IDs, etiquetas, métricas y hashes antes de puntuar ambos checkpoints una sola vez. Si no se dispone de tal conjunto, cerrar con una conclusión limitada a comparaciones retrospectivas.

**Estado al 8 de octubre de 2026:** no se halló en el workspace un conjunto nuevo que cumpla estos criterios; las alternativas públicas inspeccionadas tampoco constituyen aquí una prueba binaria de artículos lista para usar. Se prepararon el [protocolo y plantilla](final_test_step7/PROTOCOLO_PRUEBA_FINAL.md), un [auditor previo sin inferencia](step7_audit_fresh_dataset.py), la [tarjeta del candidato](final_test_step7/MODELO_NUEVO_TARJETA.md) y el [cierre retrospectivo](final_test_step7/CIERRE_RETROSPECTIVO.md). **No se puntuó un conjunto nuevo ni se afirmó generalización final.** La evaluación definitiva queda pendiente de recibir y auditar noticias inéditas con evidencia por etiqueta.

Entregar informe comparativo, predicciones por ID, manifiestos, curvas y matrices, tarjeta del nuevo modelo, limitaciones y rutas de todos los checkpoints. Ningún puntaje del clasificador se presentará como verificación factual de una noticia individual.

## Criterio de término de la ejecución futura

El trabajo estará completo cuando existan datos auditados y congelados, ejecuciones independientes sin sobrescritura, selección trazable exclusivamente por validación, comparación pareada reproducible con E1 y un informe que distinga resultados exploratorios de una prueba final inédita. Los pasos 1–6 están ejecutados. Se cerró el análisis disponible como **retrospectivo**; la afirmación de mejora sobre noticias nuevas sigue pendiente de la prueba inédita del paso 7.
