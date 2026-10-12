# BiLSTM de ScanTrue

Este directorio contiene el código, la configuración y el checkpoint seleccionado para clasificar **textos de noticias en español** de forma experimental. El modelo disponible en el repositorio es el *pequeño mejorado* con fastText CC español, semilla 42 y máximo 192 tokens BiLSTM.

## Preparar el entorno

Usa Python 3.14.4 y un entorno virtual en `bilstm/.venv`. Instala las dependencias fijadas en [`requirements.txt`](requirements.txt) y la compilación de PyTorch apropiada para tu sistema desde el [selector oficial](https://pytorch.org/get-started/locally/). Para Windows 11 con GPU, sigue [`INSTALACION_WINDOWS.md`](INSTALACION_WINDOWS.md). El entorno virtual no se guarda en Git.

## Usar el checkpoint incluido

Desde la raíz del repositorio, en Ubuntu:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py \
  --modelo datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt \
  --texto 'Titular. Texto de la noticia...' --device auto
```

El checkpoint incluye pesos y vocabulario; [`config.json`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/config.json) registra el entrenamiento. `--device auto` usa CUDA si está disponible y CPU en caso contrario. El script recibe **un solo texto**: título seguido del cuerpo, sin repetir el título. Lee como máximo los primeros **192 tokens** según [`tokenize()`](entrenar_baseline.py), no 192 caracteres. Para entradas muy breves falta contexto; no existe una longitud óptima validada.

También acepta `--archivo noticia.txt` o `--csv noticias.csv` con columna `texto`. Para guardar predicciones por fila de un CSV, añade `--salida predicciones.csv`. Si se dispone de los tres CSV locales de entrenamiento, validación y prueba, `--referencia datasets/experimentos_balanceados/pequeno_mejorado` permite detectar coincidencias con ellos. Si faltan, la predicción funciona y `referencia_disponible=false` indica que **no se pudo comprobar el solapamiento**.

## Qué se puede concluir

En una prueba exploratoria de 606 noticias de fuentes reservadas, el modelo obtuvo **F1 macro 0,603**, detectó 227 de 299 noticias falsas y marcó falsas 164 de 307 noticias reales. `prob_falsa` es una puntuación del clasificador, **no una verificación de hechos**. [Resultados y pruebas del modelo](RESULTADOS_MEJOR_MODELO.md) explica los datos, métricas y límites.

Los datasets originales, las particiones de entrenamiento, los embeddings fastText descargados y otros checkpoints **no se incluyen** en Git. El script de entrenamiento requiere esas entradas para repetir el experimento; el checkpoint incluido permite usar el modelo ya entrenado.
