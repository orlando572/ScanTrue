# BiLSTM entrenado con el conjunto unificado depurado

Se entrenó un **modelo nuevo y separado**. Ningún checkpoint anterior fue sobrescrito. La entrada fue `datasets/unificado_total/depurado/` (véase `DEPURACION_UNIFICADO.md`), adaptada al esquema que lee `bilstm/entrenar.py` en `datasets/experimentos_bilstm/unificado_depurado/datos/`. El vocabulario se creó solo con entrenamiento.

## Configuración y ejecución

- Arquitectura: BiLSTM con embeddings aprendidos de 128 dimensiones, estado oculto de 64 y abandono 0,3.
- Texto máximo: 128 tokens; vocabulario: 30 000 entradas; lote: 64.
- Optimizador AdamW; pérdida ponderada por frecuencia de clase; selección por F1 macro en validación.
- Hasta 20 épocas, paciencia de 4 y semilla 42. Se ejecutaron 14 épocas y se conservó la 10.
- Se usó **CPU**: en esta sesión `torch.cuda.is_available()` fue `False`, no había `/dev/nvidia*` y `nvidia-smi` no pudo comunicarse con el controlador.
- Checkpoint: `datasets/modelos_bilstm/unificado_depurado/mejor_modelo.pt`. Configuración, historial y métricas están en la misma carpeta.

Comando utilizado desde la raíz del proyecto:

```bash
bilstm/.venv/bin/python bilstm/adaptar_unificado.py
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 bilstm/.venv/bin/python bilstm/entrenar.py \
  --input datasets/experimentos_bilstm/unificado_depurado/datos \
  --output datasets/modelos_bilstm/unificado_depurado \
  --device cpu --epochs 20 --patience 4 --max-len 128 --batch-size 64
```

El adaptador es reproducible: al volver a ejecutarlo se obtuvieron los mismos SHA-256 de las tres particiones usadas en el entrenamiento. Para repetir la comparación después de disponer del checkpoint: `bilstm/.venv/bin/python bilstm/comparar_unificado.py --device cpu`.

## Resultados del modelo nuevo

| Conjunto | Filas | Exactitud | F1 macro | Recall de falsas |
| --- | ---: | ---: | ---: | ---: |
| Validación (mejor época) | 5 849 | 0,946 | 0,944 | 0,920 |
| Prueba interna | 5 849 | 0,938 | 0,937 | 0,909 |
| Prueba de fuentes reservadas | 606 | 0,490 | 0,423 | 0,151 |

En la prueba interna, el F1 macro por fuente fue **0,947** en Spanish Political Fake News (5 670 filas), **0,751** en PolyglotFakeFacts (82) y **0,438** en Spanish Fake News Corpus v1 (97). El promedio global interno está dominado por las noticias políticas.

En la prueba reservada había 299 falsas y 307 reales. El modelo clasificó correctamente **45 falsas** y **252 reales**; confundió 254 falsas con reales y 55 reales con falsas. Estas probabilidades y etiquetas son predicciones del modelo, no verificaciones de hechos.

## Comparación con modelos anteriores

Se evaluaron 19 checkpoints anteriores de noticias sobre **las mismas 606 filas** que el modelo nuevo. Se cotejaron texto, titular suficientemente específico, cuerpo y URL con los conjuntos anteriores de entrenamiento y validación; no se encontró solapamiento según esas reglas. El archivo `datasets/experimentos_bilstm/unificado_depurado/comparacion.json` contiene métricas y matrices de confusión de todos los modelos, también por fuente. `resumen_comparacion.csv` facilita ordenarlos.

| Modelo de noticias | F1 macro | Exactitud | Recall de falsas |
| --- | ---: | ---: | ---: |
| Mejor anterior: fastText CC, semilla 44, 192 tokens | **0,584** | 0,584 | 0,585 |
| BiLSTM anterior de 384 tokens, semilla 43 | 0,574 | 0,574 | 0,572 |
| Modelo principal anterior `sin_politica` | 0,547 | 0,550 | 0,632 |
| **Nuevo unificado, 128 tokens** | **0,423** | 0,490 | 0,151 |

Los ocho modelos de titulares se evaluaron aparte en las 534 filas con titular, pasándoles **solo el titular**. El mejor obtuvo F1 macro 0,496; esa cifra no es directamente comparable con la tabla de modelos que reciben el texto completo.

## Interpretación y límites

El entrenamiento con muchas más filas **no mejoró la generalización a estas fuentes**. Es compatible con un sobreajuste al estilo del corpus político, que representa aproximadamente el 96 % de los datos depurados: el modelo rinde muy bien en noticias políticas de su colección y falla con fuentes distintas. La diferencia de longitud de entrada y de composición del entrenamiento también afecta la comparación; por ello no se atribuye toda la caída a un único factor.

La prueba reservada quedó fuera del entrenamiento nuevo, aunque algunas de sus noticias ya se habían usado como **prueba** en experimentos anteriores. La búsqueda de solapamientos no detecta todas las paráfrasis. Para afirmar un desempeño general en noticias actuales haría falta una evaluación adicional, etiquetada de forma independiente y ajena a todas las fuentes de entrenamiento.
