# Experimentos nuevos con fuentes equilibradas y fastText

## CUDA y modelos conservados

La comprobación dentro del aislamiento no mostraba la GPU. Con acceso al equipo, `nvidia-smi` detectó la **NVIDIA GeForce RTX 3050 6 GB Laptop GPU**, y PyTorch **2.14.1+cu130** ejecutó una operación CUDA correctamente. Los tres entrenamientos nuevos registran `device: cuda` en sus respectivos `config.json`.

Se copiaron sin modificar siete checkpoints seleccionados a `datasets/modelos_seleccionados_2026-10-07/`. `MANIFIESTO.json` guarda origen, tamaño y SHA-256. Incluye el modelo principal anterior, los mejores candidatos de noticias y titulares, el unificado de 128 tokens y el mejor de esta ronda. Sus originales siguen en sus carpetas; tampoco se modificaron los CSV usados para sus resultados anteriores.

## Datos nuevos

`bilstm/preparar_balanceados.py` genera dos carpetas independientes en `datasets/experimentos_balanceados/`. Ambas usan **la misma validación (170), prueba interna (179) y prueba de fuentes reservadas (606)**. Las filas conservan identificador, fuente, etiqueta, grupo de duplicados y longitud en tokens. No hay identificadores ni grupos cruzados entre particiones.

| Conjunto | Entrenamiento | Composición del entrenamiento |
| --- | ---: | --- |
| `pequeno_mejorado` | 3 066 | Spanish Fake News Corpus v1: 769; PolyglotFakeFacts: 614; USMSC/Edds residual: 1 683. |
| `grande_balanceado` | 6 132 | Las 3 066 anteriores más 3 066 noticias políticas, seleccionadas por grupos con semilla 42. |

El entrenamiento antiguo del modelo principal tenía 1 834 filas. Para la variante pequeña nueva se excluyó la fuente Acosta, cuya clase falsa contiene sátira, y se agregaron **1 683** textos binarios residuales de USMSC/Edds tras descartar cuatro de menos de diez tokens. Estos textos derivados carecen de medio y titular verificables y algunos siguen tratando política: **equilibrar fuentes no equivale a equilibrar temas**. El conjunto grande reduce las noticias políticas en vez de duplicar las fuentes pequeñas; con los datos actuales no es posible mantener las 45 mil políticas del entrenamiento anterior y conseguir proporciones similares de filas únicas por fuente.

Los conjuntos anteriores (`datasets/experimentos_bilstm/` y `datasets/unificado_total/depurado/`) permanecen intactos.

## Entrenamientos nuevos

Todos usan BiLSTM, máximo 192 tokens, estado oculto de 64, dropout 0,3, lote 32, semilla 42 y selección por F1 macro en la validación común. Los embeddings tienen **300 dimensiones** tanto en el control aleatorio como en los modelos fastText, de modo que esa comparación mantiene igual su tamaño.

| Modelo nuevo | Mejor época | F1 macro validación | F1 macro prueba interna (179) | F1 macro fuentes reservadas (606) | Recall falsa en reservadas |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grande, aleatorio 300d | 12 | 0,672 | 0,673 | 0,571 | 0,512 |
| Grande, fastText CC español 300d | 3 | 0,712 | 0,728 | 0,587 | 0,699 |
| Pequeño mejorado, fastText CC español 300d | 8 | **0,765** | **0,774** | **0,603** | **0,759** |
| Mejor anterior de noticias, fastText CC s44 | — | — | No evaluado; particiones anteriores distintas | 0,584 | 0,585 |
| Unificado de 128 tokens anterior | 10 | — | No comparable por otra partición | 0,423 | 0,151 |

Los checkpoints nuevos se guardaron en `datasets/modelos_balanceados/`, cada uno en su carpeta. `datasets/experimentos_balanceados/comparacion.json` conserva métricas, matrices de confusión y resultados por fuente. Las pruebas internas son comparables solo entre los tres modelos nuevos. La prueba reservada ya se había consultado en rondas anteriores; la diferencia de **0,603 frente a 0,584** del mejor anterior es **exploratoria**, no una mejora confirmada para despliegue.

En las 606 noticias reservadas, el pequeño mejorado clasificó correctamente 227 de 299 falsas y 143 de 307 reales. Su recall de falsas subió, pero produjo **164 falsos positivos** frente a **128** del mejor modelo anterior. Si se prioriza no marcar noticias reales como falsas, ese costo importa.

## Longitud mínima de entrada

`bilstm/evaluar_min_tokens.py` evaluó rechazar noticias de menos de 10, 20, 30, 50, 100, 128, 192 o 384 tokens **sin reentrenar**. En las 606 noticias reservadas no hay ninguna de menos de 30 tokens, por lo que un mínimo de 10 a 30 no cambia ninguna predicción. Un mínimo de 100 deja 587 noticias (96,9 % de cobertura) y, para el pequeño mejorado, cambia el F1 macro de **0,603 a 0,604** y la tasa de falsos positivos de **0,534 a 0,533**: efecto despreciable. Un mínimo de 384 deja solo 326 noticias (53,8 % de cobertura), baja el F1 macro a **0,573** y sube la tasa de falsos positivos a **0,542**.

**Conclusión:** estos datos no respaldan imponer una longitud mínima para mejorar calidad o reducir falsos positivos. Rechazar entradas breves reduce cobertura y no corrige la causa de las predicciones erróneas. `datasets/evaluaciones_min_tokens/reporte.json` incluye todos los umbrales y modelos. Para titulares breves, un mínimo arbitrario podría descartar entradas válidas.

## Reproducibilidad y límites

```bash
bilstm/.venv/bin/python bilstm/preparar_balanceados.py
bilstm/.venv/bin/python bilstm/entrenar.py --input datasets/experimentos_balanceados/grande_balanceado --output NUEVA_CARPETA --device cuda --epochs 20 --patience 4 --max-len 192 --batch-size 32 --embedding-dim 300 --seed 42
bilstm/.venv/bin/python bilstm/preentrenados/entrenar.py --input datasets/experimentos_balanceados/grande_balanceado --output OTRA_CARPETA --embeddings datasets/embeddings_preentrenados/cc.es.300.vec.gz --source fasttext_cc --device cuda --epochs 20 --patience 4 --max-len 192 --batch-size 32 --seed 42
```

Para el pequeño mejorado, se usa `datasets/experimentos_balanceados/pequeno_mejorado` como entrada del entrenador fastText y una tercera carpeta de salida. El preparador rechaza volver a escribir carpetas existentes para proteger resultados previos.

Los resultados proceden de **una semilla** y conjuntos pequeños por fuente fuera de política. USMSC/Edds puede contener errores de etiqueta o textos derivados difíciles de rastrear. Antes de promover un modelo se necesitan varias semillas, una prueba nueva no consultada durante el desarrollo y una revisión manual de errores y licencias.
