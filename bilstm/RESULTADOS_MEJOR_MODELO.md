# Resultados y pruebas del BiLSTM seleccionado

El checkpoint incluido en este repositorio es `datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt`. Se entrenó con [`preentrenados/entrenar.py`](preentrenados/entrenar.py), fastText CC español de 300 dimensiones, semilla 42, máximo 192 tokens y CUDA. [`config.json`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/config.json) conserva los parámetros; [`resultados.json`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/resultados.json), el resultado de validación.

## Datos utilizados

La entrada fue `datasets/experimentos_balanceados/pequeno_mejorado/`. Sus CSV son artefactos locales **excluidos de Git**. El modelo recibió únicamente la columna `texto`, que incluye el titular al inicio cuando existía; `titulo` no fue una segunda entrada. La etiqueta es **`0=falsa`, `1=real`**.

| Partición | Total | Falsas | Reales | Función |
| --- | ---: | ---: | ---: | --- |
| Entrenamiento | 3.066 | 1.309 | 1.757 | Aprender los pesos |
| Validación | 170 | 81 | 89 | Elegir la mejor época |
| Prueba interna | 179 | 69 | 110 | Evaluar las fuentes conocidas |
| Fuentes reservadas | 606 | 299 | 307 | Examinar otras fuentes |

El entrenamiento reúne **769** filas de Spanish Fake News Corpus v1, **614** de PolyglotFakeFacts v2 filtrado a español y **1.683** textos binarios residuales de USMSC/Edds. Se retiró la clase de sátira, se unificó la dirección de las etiquetas y se agruparon copias o noticias relacionadas antes de separar las particiones. Los residuales de USMSC/Edds carecen de titular y medio verificables; su calidad debe interpretarse con cautela.

## Métricas registradas

| Evaluación | F1 macro | Exactitud | Precisión de falsa | Recall de falsa | Reales marcadas falsas |
| --- | ---: | ---: | ---: | ---: | ---: |
| Validación, mejor época 8 | 0,765 | 0,765 | 0,741 | 0,778 | 22 de 89 |
| Prueba interna | 0,774 | 0,782 | 0,697 | 0,768 | 23 de 110 |
| Fuentes reservadas | **0,603** | 0,611 | 0,581 | 0,759 | **164 de 307 (53,4 %)** |

Matrices de confusión (filas = etiqueta real; columnas = predicción; orden `0=falsa`, `1=real`):

- Validación: `[[63, 18], [22, 67]]`.
- Prueba interna: `[[53, 16], [23, 87]]`.
- Fuentes reservadas: `[[227, 72], [164, 143]]`.

En las fuentes reservadas detectó 227 de 299 noticias falsas y produjo 164 falsas alarmas sobre 307 noticias reales. Esta última prueba se consultó repetidamente durante los experimentos del proyecto; el **F1 macro 0,603 es una comparación exploratoria**, no una estimación independiente de producción. El modelo puede aprender rasgos de fuente o longitud y no verifica hechos con evidencia. Su salida `prob_falsa` no es una probabilidad calibrada de falsedad.

## Cómo se obtuvieron y comprobaron las predicciones

[`probar_externo.py`](probar_externo.py) carga el checkpoint y devuelve la clase, `prob_falsa` y los tokens leídos. Para evaluar los 606 textos locales se utilizó `externa.csv` de la misma carpeta de datos; ninguna fila fue excluida por duplicado o solapamiento. Las predicciones por fila se conservaron **solo localmente** en `datasets/evaluaciones_externas/pequeno_mejorado_s42_externa_predicciones.csv`, excluido de Git porque contiene textos de los datasets. Las métricas anteriores se reprodujeron con ese archivo.

Las pruebas de código relevantes son [`test_probar_externo.py`](test_probar_externo.py), [`test_entrenar.py`](test_entrenar.py) y [`preentrenados/test_entrenar.py`](preentrenados/test_entrenar.py). Comprueban la evaluación externa, el manejo de referencias ausentes, la lectura de particiones y la carga de vectores. Para instalar y usar el checkpoint, consulta el [README de BiLSTM](README.md).
