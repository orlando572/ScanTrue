# Fase E — entrenamientos mBERT y selección por validación

**Estado:** completada el 7 de octubre de 2026. **No se abrieron las pruebas reservadas** `es_test_main`, `es_test_polyglot_stress` ni `en_test_perez_rosas`; la fase F hará esa evaluación una vez fijado el candidato.

## Artefactos y control de ejecuciones

El checkpoint base oficial `google-bert/bert-base-multilingual-cased` quedó en [model_mbert_cased](assets/model_mbert_cased), formato `safetensors`, revisión `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`, la misma del tokenizador. [train_phase_e.py](train_phase_e.py) crea una carpeta **exclusiva** por experimento, longitud, semilla, fecha y sufijo aleatorio; si falla, conserva la carpeta. Dentro de cada ejecución completa hay configuración, hashes de datos/IDs, log, checkpoints por época, `best_model` y métricas de validación. Ninguna ejecución reanudó ni sobrescribió otra.

El primer diagnóstico encontró que `Trainer` con seguimiento de memoria hacía cada paso anormalmente lento. Se conservaron dos carpetas interrumpidas **sin checkpoint** y una ejecución diagnóstica de tres pasos, todas identificadas como tales en el [resumen verificable](phase_e_summary_20261007_v1/summary.json). Después se desactivó ese seguimiento, se fijaron cuatro hilos CPU y se usó `adamw_torch`; un entrenamiento E1 completo pasó a tardar menos de un minuto. También se evitó la recarga automática del mejor modelo de `Trainer` 5.19.0, que en este entorno avisaba de claves `LayerNorm` faltantes al leer checkpoints. El script elige la mejor época por F1, **carga su directorio con `from_pretrained`**, guarda una copia en `best_model` y exige que el F1 recargado coincida con el de la época elegida.

Configuración inicial: PyTorch 2.13.0+cu130, `bf16`, tres épocas, tasa `2e-5`, decaimiento 0,01, calentamiento del 10 %, lote 4 y acumulación 4 (lote efectivo 16). En 512 tokens se usaron lote 2, acumulación 8 y gradient checkpointing. El checkpoint se escogió por **F1 de FALSA en validación española** para E1/E3/E4; E2 usó solo validación inglesa. Las pruebas no participaron en entrenamiento, elección de épocas, longitudes, tasa o mezcla. El consumo máximo PyTorch del candidato E1 fue 3,406 GB de VRAM asignada.

## Comparación principal

Las cifras son **F1 de la clase FALSA en validación**, con umbral 0,5. Para configuraciones con tres semillas se muestra media ± desviación estándar muestral. [runs.csv](phase_e_summary_20261007_v1/runs.csv) contiene el F1, precisión, recall, F1 macro, tiempo y ruta de cada ejecución.

| Experimento | Longitud | Datos/ajuste | F1 validación | Semillas |
| --- | ---: | --- | ---: | ---: |
| E1 español | 128 | `es_train`, `2e-5` | 0,845 | 1 |
| E1 español | 192 | `es_train`, `2e-5` | **0,840 ± 0,014** | 3 |
| E1 español | 256 | `es_train`, `2e-5` | **0,855 ± 0,013** | 3 |
| E1 español | 512 | `es_train`, `2e-5` | 0,817 | 1 |
| E2 inglés completo | 128 | 29 949 artículos ingleses; 1 época | **0,9997 en validación inglesa** | 1 |
| E3 mixto | 128 | 667 es + 2 668 en, 20/80 | 0,842 | 1 |
| E3 mixto | 192 | 667 es + 2 668 en, 20/80 | 0,827 | 1 |
| E3 mixto | 256 | 667 es + 2 668 en, 20/80 | **0,852 ± 0,005** | 3 |
| E4 inglés→español | 192 | E2 completo + ajuste en `es_train`, `2e-5` | 0,750 | 1 |

E2 primero tuvo un piloto inglés de 2 668 registros, tres épocas, con F1 inglés 0,9996. Al saturarse pronto esa validación, se eligió 128 tokens por coste y se entrenó una época con **todo** `en_train`. Su checkpoint se fijó exclusivamente con `en_validation`. Una [evaluación diagnóstica posterior](evaluations/E2_len128_seed42_20261007-200010_933e4426_esval_20261007-201135_66a7338e/metrics.json) en `es_validation` obtuvo **F1 0,353**, precisión 0,968 y recall 0,216 para FALSA. Esto evidencia una transferencia pobre con el umbral fijo. La validación casi perfecta de ISOT está afectada por diferencias de fuente/estilo entre clases y no demuestra detección factual general.

### Búsqueda acotada

- En E1 de 256 con semilla 42, `1e-5` dio F1 **0,813**. Con `3e-5`, las semillas 42/43/44 dieron **0,864 / 0,841 / 0,844**, media aproximada **0,850**; `2e-5` promedió **0,855** con esas mismas semillas.
- En E3 de 256, la mezcla 20 % español / 80 % inglés promedió **0,852** en tres semillas. Una prueba adicional con 40 % español y semilla 42 dio **0,839**. El cambio de proporción también cambia el número de ejemplos ingleses; esta comparación es exploratoria, no un efecto aislado de proporción.
- Una segunda E4 desde el mismo checkpoint inglés, a 256 tokens y `1e-5`, dio F1 **0,649**. No mejoró la adaptación secuencial inicial.
- No se amplió el barrido inglés de longitudes: su validación interna quedó casi saturada a 128 y el coste de ISOT completo era alto. Las longitudes 128/192/256 y 512 condicional sí se entrenaron en E1, y 128/192/256 en E3.

## Decisión congelada antes de pruebas

El **candidato principal para fase F** es **E1, 256 tokens, `2e-5`, tres épocas**. Su F1 medio de tres semillas (0,8547) fue ligeramente superior al de E3 con igual longitud (0,8516). La diferencia **0,0031** es pequeña frente a la variación entre semillas; la conclusión prudente es que **añadir inglés no mostró una mejora reproducible en esta validación**. E4 rindió bastante peor en los dos ajustes probados.

Para una única predicción final, el checkpoint elegido dentro de la configuración E1 es la [ejecución semilla 44](runs/E1_len256_seed44_20261007-202946_bda20c1f/metrics_validation.json), con F1 de validación **0,8686**, precisión **0,8815** y recall **0,8561**. El archivo del modelo está en [best_model](runs/E1_len256_seed44_20261007-202946_bda20c1f/best_model), y su SHA-256 figura en [summary.json](phase_e_summary_20261007_v1/summary.json). Este valor individual está optimizado por validación; la fase F deberá informar también la variación de las tres semillas y comparar los experimentos sobre **las mismas pruebas congeladas**, sin elegir de nuevo según esos resultados.

El [resumen](phase_e_summary_20261007_v1/summary.json) verificó **23 ejecuciones con métricas**, incluidos un piloto E2 y el diagnóstico de tres pasos; **2 intentos interrumpidos** permanecen intactos. Todas las ejecuciones completas verificadas contienen su mejor modelo, el checkpoint original y F1 idéntico tras recarga. No existe `metrics_test.json` en ninguna. Las limitaciones previas siguen vigentes: pocos datos españoles, sesgo de fuente en varios corpus, prueba Polyglot solo de estrés y posibles eventos semejantes no detectados por las reglas automáticas.

**Siguiente fase:** F. Evaluar una vez los checkpoints predefinidos en `es_test_main` y, por separado, `es_test_polyglot_stress` y `en_test_perez_rosas`; reportar F1, precisión, recall, F1 macro, matriz de confusión, soporte, average precision y análisis de errores. No ajustar el modelo ni escoger un nuevo umbral al ver esas pruebas.
