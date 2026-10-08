# Prueba externa nueva: afirmaciones españolas de X-FACT

## Procedencia y alcance

Se descargaron las particiones públicas de [X-FACT, Universidad de Utah](https://github.com/utahnlp/x-fact/tree/main/data/x-fact) el 7 de octubre de 2026. Su [ficha](https://huggingface.co/datasets/utahnlp/x-fact) describe afirmaciones reales verificadas y etiquetas de veracidad; el repositorio indica licencia MIT. Ninguno de los nueve BiLSTM de la serie política se entrenó ni eligió con X-FACT.

Esta prueba **no contiene artículos completos**: son afirmaciones breves de Chequeado (Argentina), de **4 a 35 tokens**. Por ello mide cómo responden los modelos ante afirmaciones en español fuera de sus corpus previos, pero **no confirma el rendimiento en noticias largas**.

## Preparación fijada antes de evaluar

`bilstm/preparar_prueba_xfact.py` reunió las particiones originales `train.all.tsv`, `dev.all.tsv` y `test.all.tsv`. Aunque X-FACT llama *train* a una de ellas, los modelos de este proyecto jamás usaron ese corpus: las tres particiones son externas a sus entrenamientos. Se conservaron solo filas `language=es` con etiqueta **exactamente** `true` o `false` (`1=verdadera`, `0=falsa`). Se excluyeron `mostly true`, `partly true/misleading`, `other` y `complicated/hard to categorise`; no se les inventó una etiqueta binaria.

De 1 399 filas españolas, **601** tenían etiqueta estricta. Se quitaron **3** duplicados internos y **4** afirmaciones muy parecidas a titulares del corpus local (similitud TF-IDF de palabras y pares de palabras ≥ 0,70). No hubo coincidencias exactas adicionales con texto o titular normalizado. La prueba quedó fijada en **594** afirmaciones: **218 falsas y 376 verdaderas**. Ninguna supera los 192 tokens del modelo.

Los originales, sus SHA-256, los descartes y el SHA-256 del CSV final están en `datasets/pruebas_externas/x_fact/preparacion.json`. El CSV final es `datasets/pruebas_externas/x_fact/evaluacion_es_estricta.csv`. La comprobación de similitud no puede descartar todas las paráfrasis ni todos los eventos compartidos.

## Resultados sin ajustar el umbral

Se evaluaron **los nueve checkpoints existentes**, sin reentrenar ni cambiar el umbral de 0,5. Cada cifra es la media de las tres semillas, seguida de la desviación poblacional cuando corresponde. FP es una afirmación verdadera marcada como falsa.

| Proporción de fuente política en entrenamiento | F1 macro | Precisión falsa | Recall falsa | FP / 376 verdaderas | Tasa FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 % | **0,539 ± 0,008** | 0,431 | **0,344** | 99,0 | 26,3 % |
| 25 % | 0,524 ± 0,017 | 0,434 | 0,268 | 75,7 | 20,1 % |
| 50 % | 0,521 ± 0,010 | **0,440** | 0,248 | **68,7** | **18,3 %** |

| Proporción | F1 semilla 42 | F1 semilla 43 | F1 semilla 44 |
| --- | ---: | ---: | ---: |
| 0 % | 0,532 | 0,535 | **0,551** |
| 25 % | 0,538 | 0,499 | 0,533 |
| 50 % | 0,527 | 0,528 | 0,507 |

La evaluación completa se conserva localmente en `datasets/pruebas_externas/x_fact/evaluacion_modelos.json` (excluido de Git); guarda matrices de confusión, F1, precisión, recall, FP y el desglose por partición original para cada checkpoint.

## Decisión

Esta prueba nueva tampoco muestra una mejora de F1 al añadir 25 % de la fuente política: el **0 %** tuvo el F1 medio más alto. Añadir política redujo falsos positivos, pero también hizo que se escaparan más afirmaciones falsas. El recall de la clase falsa fue bajo en las tres variantes (24,8–34,4 %), una señal de que los modelos de noticias largas funcionan mal en este formato breve.

**No se promueve ningún modelo para despliegue.** La comparación anterior de artículos sigue siendo exploratoria porque su prueba reservada se había consultado varias veces; X-FACT aporta una fuente nueva, pero cambia la tarea y solo tiene un sitio. Para confirmar rendimiento en el objetivo principal aún hace falta una prueba nueva de **artículos completos en español**, con ambas clases, varios medios/temas, etiquetas verificables y control de solapamiento. Se deberá fijar el checkpoint y el umbral antes de medirla.

Después de esta comparación de nueve modelos, X-FACT también queda **consultado**. No debe reutilizarse como prueba inédita para escoger nuevos cambios del entrenamiento o del umbral.

## Reproducción

Desde la raíz del proyecto, con los TSV originales disponibles y CUDA activo:

```bash
bilstm/.venv/bin/python bilstm/preparar_prueba_xfact.py
bilstm/.venv/bin/python bilstm/evaluar_prueba_xfact.py
```

Ambos scripts rechazan sobrescribir sus resultados existentes. Los archivos grandes de `datasets/` se mantienen locales e ignorados por Git.
