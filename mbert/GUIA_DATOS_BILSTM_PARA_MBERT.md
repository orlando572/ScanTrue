# Guía para diagnosticar mBERT con los datos y resultados del BiLSTM

**Objetivo para el agente de mBERT:** averiguar por qué el modelo parece marcar casi todas las noticias como falsas y comparar cambios de forma controlada. Los resultados del BiLSTM sirven como referencia experimental; **su dataset y su arquitectura no garantizan corregir mBERT**.

## 1. Diagnóstico prioritario

Antes de reentrenar o cambiar de datos, entregar estas comprobaciones:

1. **Medir el error real.** Mostrar la matriz de confusión con filas de etiqueta verdadera y columnas de predicción, en orden `0=falsa, 1=real`; informar precisión, recall y F1 por clase, F1 macro y tasa de falsos positivos. Si el 98 % de las noticias **reales** se predice como falsas, la tasa de falsos positivos es 98 %. Verificar primero el denominador: unos casos elegidos a mano no permiten estimarla.
2. **Auditar el mapa de clases de extremo a extremo.** Revisar etiquetas originales y finales, `label2id`/`id2label`, función de pérdida, orden de los logits, regla de decisión y respuesta del backend. Confirmar con ejemplos conocidos que la salida «falsa» corresponde realmente a la clase `0`. Revisar también ponderaciones de clase, muestreo y umbral.
3. **Ver qué lee mBERT.** Inspeccionar ejemplos tokenizados y decodificados de ambas clases: título, cuerpo, separadores, campos vacíos, longitud y texto conservado después del truncamiento. Entrenamiento e inferencia deben usar el mismo formato y orden.
4. **Auditar los datos.** Contar clases por fuente y partición; revisar muestras de falsas alarmas, etiquetas ambiguas, sátira y artículos que desmienten otra afirmación. Detectar copias y noticias relacionadas antes de separar particiones. Informar resultados por fuente y por longitud.

**Separar título y cuerpo no es un fallo en sí.** mBERT puede recibir `(título, cuerpo)` como par o un texto combinado. Debe elegirse una representación y mantenerla en entrenamiento, validación e inferencia. Si se usa el CSV de este experimento, `texto` ya contiene el titular cuando existe: añadir `titulo` otra vez lo duplicaría. En los registros sin titular, evitar un primer campo vacío tratado de forma diferente entre entrenamiento y predicción.

## 2. Archivos mínimos del experimento comparable

El mejor BiLSTM se entrenó con el **conjunto final `datasets/experimentos_balanceados/pequeno_mejorado/`**, no directamente con el unificado general de más de 60.000 filas. No es un CSV único, sino estas particiones:

| Archivo | Uso | Total | Falsa (`0`) | Real (`1`) |
| --- | --- | ---: | ---: | ---: |
| `entrenamiento.csv` | Aprender pesos | 3.066 | 1.309 | 1.757 |
| `validacion.csv` | Elegir época y ajustes | 170 | 81 | 89 |
| `prueba.csv` | Comparación interna | 179 | 69 | 110 |

`externa.csv` tiene 606 noticias (299 falsas, 307 reales) de fuentes reservadas. **No se usa para entrenar ni ajustar mBERT.** Ya se consultó repetidamente al comparar BiLSTM; cualquier resultado allí es exploratorio. Para estimar rendimiento final se necesita otra prueba inédita. Los cuatro CSV están en `datasets/experimentos_balanceados/pequeno_mejorado/` y están ignorados por Git: un clon del repositorio no los contiene.

Para usar las mismas entradas: **`texto` es la entrada y `etiqueta` es el objetivo**, con `0=falsa`, `1=real`. El checkpoint BiLSTM no es necesario para entrenar mBERT.

## 3. Qué contienen y por qué se prepararon así

| Campo | Papel |
| --- | --- |
| `texto` | Texto que recibió el BiLSTM; contiene titular al inicio si existe y no estaba ya en el cuerpo. |
| `etiqueta` | Clase binaria compatible entre las fuentes incluidas. |
| `titulo` | Titular para auditoría; puede estar vacío y **no fue una segunda entrada del BiLSTM**. |
| `dataset`, `origen`, `tipo_tarea` | Fuente, procedencia y tipo de etiqueta para revisar sesgos y errores. |
| `id`, `grupo_duplicados`, `url` | Trazabilidad y control de duplicados o noticias relacionadas entre particiones. |
| `tokens` | Longitud según el tokenizador BiLSTM; **no equivale a subpalabras de mBERT**. |

Se normalizaron Unicode y espacios, se agruparon textos repetidos o relacionados por contenido, titular, cuerpo o URL y se aislaron etiquetas contradictorias. Se mantuvieron grupos completos en una partición para reducir fugas. Se excluyeron clases que no representan la misma tarea: sátira, afirmaciones sin clase real comparable, fiabilidad del medio y artículos de verificación cuyo veredicto describe una afirmación ajena.

| Fuente del entrenamiento | Filas | Falsas / reales | Etiqueta original | Particularidad |
| --- | ---: | ---: | --- | --- |
| Spanish Fake News Corpus v1 | 769 | 377 / 392 | `fake` / `true` | Titular disponible. |
| PolyglotFakeFacts v2, solo español | 614 | 237 / 377 | `fake` / `real` | Titular disponible. |
| USMSC/Edds residual | 1.683 | 695 / 988 | `0` / `1`; `2` es sátira y se excluyó | Textos derivados sin titular separado ni medio verificable. |

**Riesgo importante para mBERT:** los 1.383 ejemplos de v1 y Polyglot tienen titular, mientras que los 1.683 residuales de USMSC/Edds no. Las medianas de longitud del entrenamiento son aproximadamente **326, 586 y 43 tokens BiLSTM**, respectivamente. La presencia de título y la longitud pueden revelar la fuente; el modelo podría aprender ese atajo en vez de señales transferibles de veracidad. Medir errores por fuente y longitud, y revisar qué conserva el límite de subpalabras de mBERT.

El unificado depurado anterior tenía 59.099 noticias, aproximadamente 96 % de una fuente política. El conjunto `pequeno_mejorado` se creó aparte sin añadir esa fuente política explícita al entrenamiento; esto redujo su dominio, pero no elimina noticias políticas de las otras fuentes ni asegura etiquetas perfectas. Los residuales de USMSC/Edds merecen revisión manual de calidad.

## 4. Referencia de resultados y siguiente comparación

El mejor checkpoint BiLSTM del ranking es `datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt`: fastText CC español 300d, semilla 42, máximo **192 tokens BiLSTM**. En las 606 noticias de `externa.csv` obtuvo **F1 macro 0,603**, detectó **227 de 299 falsas** y marcó falsas **164 de 307 reales** (tasa de falsos positivos **53,4 %**). Fue el mejor **según ese criterio exploratorio**, pero tiene demasiadas falsas alarmas para verificar noticias automáticamente. Una puntuación del clasificador no es una prueba de veracidad.

Para saber si datos o formato ayudan a mBERT: primero corregir posibles errores de etiquetas o inferencia; después entrenar una variante con las **mismas tres particiones** y comparar sobre las **mismas filas**. Cambiar una cosa por experimento (datos, texto combinado frente a par, longitud, ponderación o umbral); elegir ajustes solo en validación. Presentar matrices de confusión y métricas por fuente y clase. Reservar una prueba nueva para la conclusión final. **Los 192 tokens de palabras del BiLSTM no son un valor óptimo transferible al tokenizador de mBERT.**

Si hace falta rastrear la preparación, el script que creó la carpeta es [`bilstm/preparar_balanceados.py`](../bilstm/preparar_balanceados.py); la entrada del BiLSTM está en [`bilstm/entrenar_baseline.py`](../bilstm/entrenar_baseline.py). El análisis completo de fuentes y límites está en [`bilstm/INFORME_GENERAL_MODELOS_BILSTM.md`](../bilstm/INFORME_GENERAL_MODELOS_BILSTM.md).

### Artefactos para comparar predicciones con el BiLSTM ya entrenado

Además de las particiones anteriores, si el agente necesita comparar **fila por fila** sobre la prueba reservada, entregarle:

- `datasets/experimentos_balanceados/pequeno_mejorado/externa.csv`: las 606 noticias de referencia con `id`, `texto` y `etiqueta` (archivo local excluido de Git).
- `datasets/evaluaciones_externas/pequeno_mejorado_s42_externa_predicciones.csv`: las mismas 606 filas, con `prob_falsa` y `prediccion` del BiLSTM (archivo local excluido de Git). `prediccion=0` significa falsa y `prediccion=1` real. No hubo solapamientos ni duplicados excluidos en esta ejecución.
- [`mejor_modelo.pt`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt) y su [`config.json`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/config.json): checkpoint y configuración si también quiere ejecutar el BiLSTM. Para **solo comparar predicciones ya generadas**, basta con los dos CSV anteriores.

El checkpoint no es un modelo mBERT: para cargarlo se requiere la clase `BiLSTM` de [`entrenar_baseline.py`](../bilstm/entrenar_baseline.py) y el cargador de [`probar_externo.py`](../bilstm/probar_externo.py), además de PyTorch. Las predicciones se generaron con ese script en CPU, sin reentrenar; reprodujeron la matriz `[[227, 72], [164, 143]]` en orden de filas/columnas `[0=falsa, 1=real]`.
