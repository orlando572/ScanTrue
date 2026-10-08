# Entrenamiento principal del BiLSTM

El script `entrenar.py` usa por defecto la variante `sin_politica`, elegida en
la comparación inicial. Entrena con **todas sus 1834 noticias de
entrenamiento**, selecciona el mejor modelo con 294 noticias de validación y
evalúa al final las 807 noticias de prueba. Las 611 noticias políticas del otro
experimento no se incorporan a este modelo.

## Ejecutar en Ubuntu con GPU

Desde la raíz del repositorio, después de preparar los datos y el entorno:

```bash
bilstm/.venv/bin/python bilstm/preparar_experimentos.py
bilstm/.venv/bin/python bilstm/entrenar.py
```

El script requiere CUDA por defecto y falla con un mensaje claro si la GPU no
está disponible. `--device cpu` permite una ejecución en CPU. Para otra
variante usa `--variant politica_25`. `--epochs`, `--patience`, `--batch-size`,
`--max-len`, `--vocab-size`, `--embedding-dim`, `--hidden-dim`, `--dropout`,
`--lr`, `--weight-decay` y `--seed` permiten ajustar el entrenamiento. Usa
`--help` para ver todos los argumentos.

La configuración predeterminada tiene BiLSTM bidireccional con embeddings de
128 y estado oculto de 64 por dirección, máximo de 192 tokens, dropout 0,3,
AdamW, pesos de clase, lote de 32, hasta 30 épocas, paciencia de 5 y semilla
42. El vocabulario se aprende solo del entrenamiento. La mejor época se elige
por F1 macro en validación; la prueba se evalúa después de elegirla. Se reduce
la tasa de aprendizaje cuando se estanca la validación y se recorta el
gradiente para dar estabilidad.

## Archivos generados

Los resultados se guardan en `datasets/modelos_bilstm/sin_politica/`, carpeta
local ignorada por Git:

- `config.json`: parámetros, versiones, cantidad de noticias y SHA-256 de las
  tres particiones usadas.
- `historial.json`: pérdida de entrenamiento y métricas de validación por época.
- `mejor_modelo.pt`: pesos, vocabulario, dimensiones y etiquetas del modelo
  seleccionado.
- `resultados.json`: métricas de prueba globales y por fuente.

Si la carpeta de salida ya contiene archivos, el programa evita sobrescribirla.
Para volver a entrenar allí, añade `--overwrite`; para preservar ambas
ejecuciones, pasa otra carpeta con `--output`.

## Ejecución verificada en este equipo

Con PyTorch 2.14.1+cu130 y la GPU NVIDIA, el entrenamiento terminó tras 25
épocas por parada temprana. La mejor fue la época 20. Sobre la prueba común:

| Métrica | Resultado |
| --- | ---: |
| Exactitud | 61,46 % |
| Precisión para falsa | 57,92 % |
| Recall para falsa | 67,19 % |
| F1 para falsa | 62,21 % |
| F1 macro | 61,45 % |

El F1 macro de FakeDeS fue 55,66 %. Los resultados son exploratorios: se
eligió la variante usando esta misma prueba en la comparación inicial. Para
estimar rendimiento final sin ese sesgo hace falta otro conjunto externo.
Además, la pérdida de entrenamiento cayó casi a cero mientras el F1 de
validación quedó cerca de 65 %, indicio de sobreajuste. No conviene tratar este
modelo como detector fiable para noticias reales sin ampliar datos y repetir
la evaluación.
