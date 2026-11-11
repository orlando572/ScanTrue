# Informe general de los modelos BiLSTM de ScanTrue

**Fecha de corte:** 7 de octubre de 2026

**Alcance:** inventario de datos, preparación, entrenamientos y evaluaciones ya realizados. Este informe se redactó con los archivos existentes; no se ejecutaron nuevos entrenamientos ni pruebas para elaborarlo.

## 1. Resumen ejecutivo

ScanTrue ha entrenado varios clasificadores BiLSTM para distinguir textos de noticias **falsas (`0`)** y **reales (`1`)** en español. El mejor checkpoint individual según el **F1 macro en una prueba común de 606 noticias** es el modelo *pequeño mejorado con fastText CC 300d, 192 tokens y semilla 42*: **F1 macro 0,603**. Detectó 227 de 299 noticias falsas, pero también señaló como falsas **164 de 307 noticias reales**. Por eso es el primero del ranking experimental, no un verificador de hechos listo para desplegar.

Los hallazgos principales son:

- **La calidad, variedad y compatibilidad de las etiquetas importaron más que la cantidad bruta de filas.** Un modelo entrenado con 46.795 filas del conjunto depurado obtuvo F1 macro 0,937 en su prueba interna dominada por la fuente política, pero solo 0,423 en las 606 noticias de fuentes reservadas.
- **fastText preentrenado ayudó en una comparación controlada**, aunque no resolvió la generalización: en el conjunto grande balanceado y con la misma semilla 42, el F1 externo fue 0,587 con fastText CC 300d frente a 0,571 con embeddings aleatorios de 300 dimensiones.
- **Más contexto puede ayudar dentro de una distribución**, pero no garantiza mejores noticias externas. Pasar de 192 a 512 tokens elevó el F1 medio de validación del experimento de longitud de 0,646 a 0,693; en la prueba común de 606, los mejores modelos fueron de 192 tokens.
- **Añadir 25 % de la fuente política explícita no mejoró el F1 medio.** Con tres semillas, el F1 en la prueba interna bajó de 0,749 a 0,721; en la prueba reservada bajó de 0,587 a 0,548.
- **Todavía falta una prueba independiente de artículos completos en español.** Las 606 noticias se han consultado repetidamente. La prueba nueva X-FACT contiene afirmaciones muy breves, por lo que mide otra situación de uso.

## 2. Fuentes de datos y decisiones de inclusión

Los originales están bajo `datasets/servir_directamente/`, `datasets/no_directamente/` y `datasets/MIS DATASETS/`. El inventario de enlaces, descargas y licencias está en [DATASETS_NOTICIAS_FALSAS_ES.md](../datasets/DATASETS_NOTICIAS_FALSAS_ES.md). Se encontraron fuentes con noticias binarias, colecciones derivadas y corpus de tareas relacionadas. **No se combinaron automáticamente todas sus etiquetas.**

| Fuente | Qué aporta | Uso en el proyecto |
| --- | --- | --- |
| **Spanish Fake News Corpus v1** | 971 noticias españolas originales, 491 reales y 480 falsas, con titular, cuerpo y tema. | Fuente binaria de entrenamiento, validación y prueba, respetando particiones y grupos de duplicados. Aporta **769** filas al entrenamiento pequeño mejorado. |
| **PolyglotFakeFacts v2** | Artículos multilingües `fake/non-fake`. | Se filtraron solo los registros declarados en español. Aporta **614** filas al entrenamiento pequeño mejorado y aparece en la prueba interna. Sus archivos organizados por clase son vistas de los mismos ejemplos, no noticias adicionales. |
| **Spanish Political Fake News** | 57.231 filas originales, casi todas sobre política; algunas noticias falsas se construyeron modificando noticias reales. | Fuente binaria válida para experimentos, pero dominante y con posible señal artificial de redacción. Aporta **1.022** filas a la variante del 25 % y **3.066** a la del 50 %. En el conjunto depurado grande aporta la mayoría de las filas. |
| **USMSC / Edds** | Corpus derivado de 61.674 registros con clases real, falsa y sátira; Edds contiene los mismos registros/etiquetas. | Se comparó con sus fuentes originales. Tras retirar correspondencias y sátira, **1.683** textos binarios residuales entraron en el entrenamiento pequeño mejorado. Su procedencia editorial es menos verificable. |
| **FakeDeS (Spanish Fake News Corpus v2)** | Noticias y publicaciones en español con clases verdadera/falsa. | Reservado principalmente para evaluación; **570** de las 606 filas de la prueba común proceden de aquí. El `test.xlsx` del repositorio de jpposadas es esta misma fuente, no otro dataset independiente. |
| **FalleDesinfo_ES** | 33 textos sobre rumores y noticias de fallecimientos. | Reservado para prueba: `T1 → falsa`, `T2/T3 → real`. Solo cubre dos acontecimientos y aporta **33** de las 606 filas. |
| **Spanish Fake and Real News (Acosta)** | 598 registros originales; una parte de la clase `fake` contiene sátira. | Se usó en experimentos tempranos; después se retiró completo de los conjuntos depurados/balanceados para evitar equiparar sátira con desinformación. |
| **FakeCovid** | Artículos que verifican o desmienten afirmaciones sobre COVID-19. | Excluido del entrenamiento binario: la etiqueta puede describir la afirmación comentada, no la veracidad del propio artículo. |
| **FactOReS** | Afirmaciones, evidencias y etiquetas `Supported/Refuted/Not Enough Evidence`. | Conservado aparte: es una tarea de verificación con evidencia, no clasificación binaria de artículos. |
| **Spanish Fake News Dataset de Zenodo** | Afirmaciones falsas y materiales de verificación. | Excluido del entrenamiento binario porque no ofrece una clase comparable de artículos reales. |
| **RUN-AS y FLARES** | Fiabilidad periodística y anotaciones por segmentos. | Conservados como tareas distintas: «fiable» no equivale necesariamente a «factualmente verdadero». |
| **MM-COVID** | Potencial corpus multilingüe de noticias COVID. | No incorporado: la descarga indicada en la fuente consultada para el inventario no estaba disponible en ese momento. |
| **X-FACT** | Afirmaciones verificadas en español de Chequeado. | Prueba nueva de textos breves, **nunca entrenamiento**. Se conservaron 594 ejemplos de etiquetas estrictas tras filtrar solapamientos. |

Las carpetas de `MIS DATASETS` incluían copias de jpposadas, USMSC y FactOReS; se compararon archivos y contenido para evitar contarlas otra vez. El origen de cada fila se preservó siempre que fue posible.

## 3. Cómo se estandarizaron y depuraron los datos

La preparación inicial está en [`preparar_datasets.py`](preparar_datasets.py); la unificación de todas las fuentes locales, en [`unificar_todos.py`](unificar_todos.py); y la limpieza con nuevas particiones, en [`depurar_y_particionar.py`](depurar_y_particionar.py). Estos procesos **no modifican los originales**.

1. **Unidad de análisis y texto de entrada.** El objetivo principal es clasificar una noticia textual. La columna común `texto` conserva el cuerpo y, cuando procede, el titular al inicio. No se entrenó únicamente con títulos. Metadatos como `dataset`, `fuente`, `url`, `fecha`, `tema`, identificador y longitud en tokens permiten auditar resultados, pero **no se pasan como características al BiLSTM**.
2. **Etiquetas compatibles.** Se fijó `0=falsa`, `1=real` solo cuando la etiqueta original tenía un significado binario compatible. Se conservó la etiqueta original para trazabilidad. Sátira, fiabilidad, afirmaciones sin clase real, artículos de verificación y etiquetas ambiguas quedaron fuera de los CSV de entrenamiento binario o en archivos auxiliares.
3. **Normalización y duplicados.** Se armonizaron espacios y Unicode. Para detectar textos repetidos se construyó una huella que ignora mayúsculas, acentos y puntuación. Se compararon también titulares, URL y, para USMSC/Edds, descripciones sin titular: una copia derivada puede haber perdido el encabezado. El unificador registró **8.945 registros repetidos por contenido** y tres pares adicionales unidos por URL y texto muy similar. Una contradicción de etiqueta para el mismo contenido se aisló en vez de elegir una clase arbitraria.
4. **Grupos y particiones.** Las noticias que comparten texto, titular suficientemente específico, cuerpo o URL se asignan al mismo grupo antes de separar entrenamiento, validación y prueba. Así se evita que una versión casi idéntica aparezca a ambos lados. FakeDeS y FalleDesinfo se apartaron por fuente. Los controles automáticos no detectan todas las paráfrasis ni artículos sobre el mismo hecho.
5. **Vocabulario y tokens.** El vocabulario de cada checkpoint se construyó **solo con su entrenamiento**. La tokenización produce palabras que se convierten en índices; las secuencias se recortan al máximo configurado y se rellenan dentro del lote. Una palabra desconocida usa el índice de desconocido. Un límite de 192 tokens se refiere al texto tokenizado, **no a 192 caracteres**.

El conjunto unificado llegó a **76.948 textos únicos de varias tareas**. De ellos, **59.699** eran noticias binarias directas y **61.387** al añadir **1.688** textos binarios derivados únicos. El depurador partió de los 59.699 binarios directos y conservó **59.099** tras excluir 600 filas problemáticas; las dividió en **46.795** para entrenamiento, **5.849** para validación, **5.849** para prueba interna y **606** de fuentes reservadas. Estos conteos describen **una línea experimental distinta** de los conjuntos balanceados. Véanse [UNIFICADO_TOTAL.md](UNIFICADO_TOTAL.md) y [DEPURACION_UNIFICADO.md](DEPURACION_UNIFICADO.md).

### Por qué algunos modelos usaron solo 3.066 o 6.132 filas

**No es correcto decir que las más de 60.000 filas eran todas duplicadas.** En USMSC/Edds se identificaron **50.997** textos derivados de fuentes ya presentes, y había copias adicionales; sin embargo, el conjunto depurado aún tenía **59.099 noticias**, de las cuales **56.761 (≈96 %)** procedían del corpus político. Muchos de esos registros políticos eran únicos. El problema era la concentración de fuente/tema y la diferencia entre tareas, además de los duplicados.

Se hizo un entrenamiento grande con **46.795** filas. Su F1 macro de prueba interna fue **0,937**, pero cayó a **0,423** en las 606 noticias reservadas: una señal clara de que la métrica interna reflejaba sobre todo el estilo de la fuente dominante. Para estudiar otra composición se construyeron conjuntos **separados, sin borrar el grande**:

| Conjunto definitivo para la serie balanceada | Entrenamiento | Composición | Validación | Prueba interna | Prueba reservada |
| --- | ---: | --- | ---: | ---: | ---: |
| `pequeno_mejorado` | **3.066** | v1: 769; Polyglot: 614; USMSC/Edds residual: 1.683 | 170 | 179 | 606 |
| `pequeno_politica_25` | **4.088** | Las 3.066 anteriores + 1.022 de la fuente política | 170 | 179 | 606 |
| `grande_balanceado` | **6.132** | Las 3.066 anteriores + 3.066 de la fuente política | 170 | 179 | 606 |

El conjunto de 25 % está contenido dentro del de 50 % respecto a la selección política. «0 %, 25 % y 50 % de política» indica la **proporción de la fuente política explícita en el entrenamiento**: otros textos también pueden hablar de política. Los tres conjuntos tienen archivos de validación y prueba **idénticos**, lo que permite compararlos en esa ronda. Las carpetas y recuentos se documentan en [RESULTADOS_BALANCEADOS.md](RESULTADOS_BALANCEADOS.md) y [EXPERIMENTO_POLITICA_25.md](EXPERIMENTO_POLITICA_25.md).

## 4. Entrenamiento y criterios de evaluación

Todos los modelos del ranking son **BiLSTM bidireccionales** que leen hasta **192 tokens** y usan embeddings **fastText CC español de 300 dimensiones** como inicialización; los embeddings se ajustan durante el entrenamiento. Comparten estado oculto de 64 por dirección, dropout 0,3, lotes de 32, optimizador AdamW y pérdida ponderada por clase. La mejor época se escogió por **F1 macro de validación**, con parada temprana; las semillas cambian la inicialización y el orden de entrenamiento. Los checkpoints del ranking registran entrenamiento en **CUDA**.

La evaluación distinguió tres funciones:

| Conjunto | Función y tamaño | Qué se puede concluir |
| --- | --- | --- |
| **Validación** | 170 noticias en la serie balanceada; 294 en la línea original. | Sirve para elegir la época. No es una estimación final: intervino en el entrenamiento. |
| **Prueba interna** | 179 noticias en la serie balanceada; 5.849 en el experimento grande depurado. | Mide desempeño dentro de las fuentes y reglas de partición de cada experimento. No se comparan directamente F1 de pruebas internas **diferentes**. |
| **Fuentes reservadas comunes** | **606 noticias: 299 falsas y 307 reales**; 570 de FakeDeS, 33 de FalleDesinfo y 3 relacionadas con v1. | Permite ordenar checkpoints de noticias sobre **las mismas filas**. Ya se consultó en varias rondas; por tanto, el ranking es exploratorio y puede estar sesgado por selección repetida. |
| **X-FACT español** | **594 afirmaciones**, 218 falsas y 376 verdaderas, de 4 a 35 tokens. | Prueba nueva de afirmaciones breves. No mide artículos completos y, tras la comparación realizada, tampoco debe volver a tratarse como inédita. |

La prueba de 606 no formó parte de los entrenamientos de la serie balanceada. Se revisaron grupos y solapamientos textuales con particiones de entrenamiento/validación, pero siempre pueden quedar acontecimientos compartidos o paráfrasis. La prueba original de 807 noticias del primer modelo **no es equivalente** a la de 606: no se deben mezclar sus F1 para ordenar los modelos. El ranking de la sección siguiente usa exclusivamente los **606 mismos ejemplos** y excluye modelos que reciben solo titulares. Hay **28 checkpoints de noticias únicos** en esa comparación, una vez retiradas copias idénticas de pesos.

### Métricas elegidas y su interpretación

| Métrica | Qué responde | Por qué se informa |
| --- | --- | --- |
| **Matriz de confusión** | Cuenta falsas acertadas, falsas perdidas, reales acertadas y reales señaladas como falsas. | Muestra el tipo de error que un número agregado puede esconder. La clase `0` es falsa; en los reportes la matriz se ordena `0=falsa, 1=real`. |
| **Precisión de «falsa»** | Entre las noticias marcadas falsas, ¿cuántas realmente tenían esa etiqueta? | Baja cuando el modelo acusa erróneamente noticias reales. |
| **Recall de «falsa»** | Entre las noticias etiquetadas falsas, ¿cuántas detectó? | Baja cuando deja pasar desinformación. |
| **F1 de «falsa»** | Media armónica de precisión y recall de falsa. | Resume el equilibrio de esos dos objetivos para la clase de interés. |
| **F1 macro** | Promedio del F1 de falsa y del F1 de real. | Es el criterio principal del ranking porque considera **ambas clases** sin dejar que la clase más abundante domine. |
| **Exactitud** | Porcentaje total de aciertos. | Es intuitiva, pero sola puede engañar cuando cambian las proporciones de clases o fuentes. |
| **Falsos positivos y tasa FP** | Noticias reales marcadas falsas; la tasa divide ese número entre las reales. | Es un daño práctico importante para un detector de noticias. |

También se informó por **fuente**. Una media global puede ocultar un resultado malo en un medio o dominio pequeño; las fuentes con pocos ejemplos no permiten conclusiones estables. Las probabilidades del clasificador **no se calibraron como probabilidades de verdad factual**.

## 5. Los cinco checkpoints mejor ubicados

**Criterio de posición:** F1 macro individual, descendente, en las **606 noticias reservadas comunes**. Las cifras de F1 próximas entre sí —especialmente los puestos 3 a 5— no demuestran diferencias estadísticamente fiables. «FP» usa como denominador las **307 noticias reales** de esa prueba.

| Puesto | Checkpoint y entrenamiento | F1 macro | Exactitud | Precisión falsa | Recall falsa | FP / 307 reales |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| **1** | **Pequeño mejorado, fastText CC, semilla 42**; 3.066 filas; [checkpoint](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt) | **0,603** | 0,611 | 0,581 | **0,759** | 164 (53,4 %) |
| **2** | **Pequeño mejorado, fastText CC, semilla 44**; 3.066 filas; checkpoint local: `datasets/modelos_balanceados/serie_politica/pequeno_mejorado_fasttext_cc300_s44/mejor_modelo.pt` | 0,591 | 0,594 | 0,574 | 0,686 | 152 (49,5 %) |
| **3** | **Grande balanceado, fastText CC, semilla 44**; 6.132 filas; checkpoint local: `datasets/modelos_balanceados/serie_politica/grande_balanceado_fasttext_cc300_s44/mejor_modelo.pt` | 0,587 | 0,587 | 0,576 | 0,622 | 137 (44,6 %) |
| **4** | **Grande balanceado, fastText CC, semilla 42**; 6.132 filas; checkpoint local: `datasets/modelos_balanceados/grande_fasttext_cc300_s42/mejor_modelo.pt` | 0,587 | 0,591 | 0,570 | 0,699 | 158 (51,5 %) |
| **5** | **Sin política original, fastText CC, semilla 44**; 1.834 filas; checkpoint local: `datasets/modelos_preentrenados/noticias_192/fasttext_cc_s44/mejor_modelo.pt` | 0,584 | 0,584 | 0,578 | 0,585 | **128 (41,7 %)** |

**Por qué están en ese orden y cuándo preferirlos:**

1. El **puesto 1** tiene el F1 macro y recall de falsa más altos; detecta más noticias falsas. Su límite inmediato son **164 falsas alarmas** sobre 307 reales: no conviene usarlo para etiquetar públicamente noticias sin revisión humana.
2. El **puesto 2** usa los mismos datos y arquitectura con otra semilla. Pierde algo de recall/F1 y reduce las falsas alarmas a 152; confirma que la semilla afecta el resultado.
3. El **puesto 3** añade la fuente política hasta 50 %. Su F1 queda cerca del segundo y baja a 137 falsas alarmas, con menor recall de falsa. Es un compromiso experimental si importa reducir acusaciones erróneas.
4. El **puesto 4** tiene un F1 casi empatado con el tercero (diferencia ≈0,0005 antes de redondear). Recupera más falsas, a costa de 21 falsas alarmas adicionales. **No hay base sólida para afirmar que el puesto 3 sea intrínsecamente mejor.**
5. El **puesto 5**, entrenado con menos datos de la línea original, tiene el **menor número de falsos positivos** de estos cinco. También detecta menos noticias falsas. No tiene una prueba interna de 179 filas comparable con la serie balanceada porque procede de otras particiones.

El modelo original de 192 tokens **sin embeddings preentrenados** (embeddings aprendidos de 128 dimensiones) quedó en el **puesto 17 de 28** por este mismo criterio, con F1 macro **0,547**. El control de 192 tokens con embeddings aleatorios de 300 dimensiones quedó en el puesto 13, F1 **0,558**. Esto aclara la comparación con fastText, sin convertir el ranking en una prueba causal de cada cambio.

### Scripts y ubicaciones de los cinco modelos

| Puestos | Datos de entrada | Script de preparación | Script que entrenó | Carpeta de checkpoint |
| --- | --- | --- | --- | --- |
| **1 y 2** | `datasets/experimentos_balanceados/pequeno_mejorado/` | [`preparar_balanceados.py`](preparar_balanceados.py) | [`preentrenados/entrenar.py`](preentrenados/entrenar.py). La semilla 44 se lanzó mediante [`entrenar_serie_politica.py`](entrenar_serie_politica.py). | `datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/` y `datasets/modelos_balanceados/serie_politica/pequeno_mejorado_fasttext_cc300_s44/` |
| **3 y 4** | `datasets/experimentos_balanceados/grande_balanceado/` | [`preparar_balanceados.py`](preparar_balanceados.py) | [`preentrenados/entrenar.py`](preentrenados/entrenar.py). La semilla 44 se lanzó mediante [`entrenar_serie_politica.py`](entrenar_serie_politica.py). | `datasets/modelos_balanceados/serie_politica/grande_balanceado_fasttext_cc300_s44/` y `datasets/modelos_balanceados/grande_fasttext_cc300_s42/` |
| **5** | `datasets/experimentos_bilstm/sin_politica/` | [`preparar_experimentos.py`](preparar_experimentos.py) | [`preentrenados/entrenar.py`](preentrenados/entrenar.py), variante fastText CC semilla 44. | `datasets/modelos_preentrenados/noticias_192/fasttext_cc_s44/` |

Cada carpeta de modelo guarda `config.json`, `historial.json`, `resultados.json` y `mejor_modelo.pt`; el checkpoint contiene los pesos y vocabulario. La evaluación comparable de los modelos anteriores está en `datasets/experimentos_bilstm/unificado_depurado/comparacion.json`; la de la serie balanceada, en `datasets/experimentos_balanceados/serie_politica/comparacion.json`. Los datos y checkpoints bajo `datasets/` están **ignorados por Git** y se conservan localmente: clonar solo el repositorio no los recupera.

## 6. Lo aprendido de los experimentos

### Longitud máxima y longitud mínima

En el modelo original, **259 de 294** noticias de validación superaban 192 tokens y eran truncadas. Comparar 192, 384 y 512 tokens con tres semillas elevó el F1 macro medio de validación de **0,646 → 0,684 → 0,693**. Es evidencia de que más cuerpo puede aportar información *en esa validación*. Sin embargo, las pruebas externas comunes situaron por delante modelos de 192 tokens: la ganancia de validación no se trasladó de manera garantizada a otras fuentes. Una noticia falsa reciente sobre teletrabajo en el MINSA, ya conocida durante el desarrollo, fue acertada por el modelo de 192 y fallada por uno de 512 pese a tener solo 56 tokens; el problema en ese caso no era el truncamiento.

Tampoco se encontró ventaja en imponer una **longitud mínima** a las entradas: en las 606 noticias no había ninguna por debajo de 30 tokens, y exigir 100 tokens cambió el F1 del mejor modelo apenas de **0,603 a 0,604** mientras rechazaba 19 noticias. X-FACT, con afirmaciones de 4–35 tokens, dio F1 macro medio **0,539** para la variante sin política y recall de falsa **0,344**; es un formato distinto, en el que estos modelos rinden peor. El número de tokens indica cuánto texto puede leer el modelo, **no cuánto contexto factual tiene**.

### Embeddings y tamaño del entrenamiento

fastText CC 300d aporta representaciones aprendidas previamente de español. En la comparación más controlada disponible, el conjunto grande balanceado con semilla 42 y 192 tokens pasó de F1 externo **0,571** con embeddings aleatorios 300d a **0,587** con fastText 300d. Es una mejora modesta bajo esas condiciones, no una garantía para cualquier dataset, semilla o noticia.

El crecimiento de **1.834 → 3.066** filas, junto con cambios de composición, produjo el mejor resultado individual. Los puestos 1 y 5 **usan ambos fastText**, pero también tienen distinta semilla y particiones de validación; **no se puede atribuir toda la mejora a sumar filas**. El entrenamiento de **46.795** filas mostró el efecto opuesto fuera de su fuente dominante. El experimento de **3.066 → 4.088 → 6.132** filas políticas es más específico: con tres semillas, añadir 25 % no aumentó el F1 medio; 50 % redujo falsos positivos en la reserva, pero sacrificó recall de falsa. Más registros de una fuente predominante pueden enseñar sus patrones particulares sin enseñar a verificar noticias de otras fuentes.

### Por qué la mejora del BiLSTM se estanca

El BiLSTM aprende regularidades en las palabras y su secuencia. Los embeddings preentrenados y más tokens pueden mejorar esas representaciones, pero **el modelo no consulta fuentes actualizadas, documentos oficiales ni evidencia para comprobar la afirmación**. Una noticia real inusual puede parecerse estilísticamente a los bulos del entrenamiento, y una falsa bien redactada puede parecerse a una noticia real. Cambiar el tamaño del corpus, la longitud o la semilla no resuelve por sí solo esa carencia.

Además, los datos abiertos en español reunidos aquí tienen límites concretos: dominio político muy grande frente a pocas noticias de otros temas; sátira y fiabilidad que no equivalen a la etiqueta falsa/real; copias entre repositorios; materiales derivados sin procedencia editorial completa; y pruebas externas pequeñas o concentradas en una fuente. **Eso no significa que el BiLSTM sea imposible de mejorar.** Significa que las mejoras observadas hasta ahora son modestas e inestables al cambiar de fuente, y que la siguiente mejora fiable requiere datos mejor verificados y evaluación mejor separada, posiblemente junto con métodos que recuperen evidencia.

## 7. Cómo interpretar los resultados y límites de uso

- **Una predicción no es un veredicto.** `prob_falsa=0,99` es una salida del clasificador basada en patrones aprendidos; no expresa 99 % de certeza factual. El proyecto ya observó errores con puntuaciones muy altas. Fecha, país, contexto y evidencia externa pueden cambiar la veracidad de una afirmación.
- **Falsos positivos altos.** El puesto 1 etiquetó como falsas **164/307 noticias reales** en la reserva. Cambia la fuente predominante entre entrenamiento y prueba; además, el entrenamiento pondera clases y aplica un umbral fijo de 0,5 a puntuaciones no calibradas. Estilo editorial, etiquetas imperfectas y falta de variedad temática pueden inducir asociaciones espurias. Son explicaciones plausibles, **no causas demostradas** de cada uno de los 164 errores; para distinguirlas habría que revisar manualmente esos casos y evaluar otros umbrales en una validación apropiada.
- **Falsos negativos también importan.** El puesto 5 reduce falsas alarmas a 128, pero su recall de falsa cae a 0,585; elegirlo sacrifica detección de bulos. La decisión depende del costo de cada error, que aún no se ha fijado para un producto real.
- **Métricas por fuente y muestra.** FakeDeS representa 570/606 ejemplos de la prueba común. FalleDesinfo solo tiene 33 y v1 solo tres en esa reserva; sus porcentajes fluctúan mucho con uno o dos errores. Una cifra global no representa todos los temas, países, fechas ni medios hispanohablantes.
- **Selección repetida.** La misma reserva de 606 se usó para estudiar numerosos checkpoints y decidir qué variantes parecían mejores. Eso hace que el «mejor F1» sea una clasificación **exploratoria**, no una estimación imparcial de producción. X-FACT fue nuevo, pero evalúa afirmaciones cortas de un solo sitio y, tras consultarlo, tampoco debe reutilizarse como prueba inédita.
- **Truncamiento y entrada.** Los modelos del top 5 leen los primeros 192 tokens del texto que se les pasa. Si el hecho decisivo aparece después, no lo ven. Un titular aislado y un artículo completo son condiciones de entrada distintas; los modelos de titulares se evaluaron aparte.

**Recomendación de uso actual:** conservar estos checkpoints como **prototipos de investigación y apoyo a revisión humana**, no para declarar automáticamente que una noticia es falsa o verdadera. Si se prioriza F1 y detección de falsas en la prueba disponible, el puesto 1 es el candidato experimental; si preocupa más acusar una noticia real, el puesto 5 tuvo menos falsas alarmas entre esos cinco, a costa de menor detección. Ninguna elección está confirmada para despliegue.

La siguiente evaluación decisiva debería reunir **artículos completos inéditos en español**, de varias fuentes y temas, con ambas clases y etiquetas verificables. Debe fijarse un checkpoint y un umbral antes de observar sus resultados, comprobar duplicados y eventos compartidos, e informar matrices de confusión, F1, precisión, recall y falsas alarmas por fuente. Comparar después una referencia sencilla y un modelo con recuperación de evidencia ayudaría a saber si conviene seguir afinando el BiLSTM.

### Uso práctico cuando la entrada llega desde una extensión web

Si una persona selecciona texto en una página, el backend debería formar la entrada con **el titular y el fragmento del cuerpo seleccionado**, en ese orden y sin repetir el titular. El modelo de noticias del top 5 fue entrenado con titular y cuerpo cuando estaban disponibles; **un titular aislado no equivale a una noticia completa**. El backend debe contar los tokens con [`tokenize()`](entrenar_baseline.py) y mostrar cuántos leerá el checkpoint.

**No se ha demostrado una longitud óptima exacta.** Como pauta de uso, conviene incluir el titular y suficiente contexto para acercarse a **150–180 tokens**, siempre que el texto original lo permita. Los modelos del ranking leen **como máximo 192 tokens**, no 192 caracteres: todo lo que quede después se ignora. No se debe rellenar ni repetir contenido para alcanzar una cifra. Si solo hay un título o una frase breve, se puede procesar, pero conviene mostrar una advertencia de contexto limitado y apoyarse más en el otro sistema o en revisión humana; no hay un mínimo validado que garantice precisión.

**Ejemplo ficticio de entrada:** el contenido del titular y el cuerpo suma **176 tokens** según el tokenizador del BiLSTM, sin contar los rótulos «Titular» y «Texto», que solo separan visualmente las partes. Cabe completo en un modelo de 192 tokens. Ilustra tamaño y formato; **no es una noticia verificada**.

> **Titular:** La municipalidad anuncia cambios en el horario de atención de los centros de salud.
>
> **Texto:** Según un comunicado publicado este lunes, cinco centros atenderán una hora más por la tarde a partir de la próxima semana. La medida se aplicaría durante tres meses y busca reducir el tiempo de espera de los pacientes. El documento indica que la atención de urgencias continuará durante su horario habitual y que las citas ya programadas no tendrán que solicitarse nuevamente.
>
> La municipalidad informó que publicará en su página oficial los nombres de los centros incluidos, las fechas de inicio y los teléfonos para consultas. También señaló que revisará cada dos semanas la cantidad de pacientes atendidos y las quejas recibidas para decidir si mantiene o ajusta la ampliación.
>
> Vecinos de distintos barrios pidieron que los nuevos horarios se coloquen en la entrada de cada establecimiento antes del cambio. Personal de salud consultado explicó que todavía espera instrucciones sobre la distribución de turnos. La autoridad local dijo que comunicará esos detalles cuando termine la coordinación con los responsables de los centros.

## 8. Mapa de archivos complementarios

| Tema | Archivo existente |
| --- | --- |
| Inventario de fuentes y enlaces | [DATASETS_NOTICIAS_FALSAS_ES.md](../datasets/DATASETS_NOTICIAS_FALSAS_ES.md) |
| Reglas de estandarización inicial | [PREPARACION_DATOS.md](PREPARACION_DATOS.md) |
| Unificación y duplicados | [UNIFICADO_TOTAL.md](UNIFICADO_TOTAL.md) |
| Depuración y particiones | [DEPURACION_UNIFICADO.md](DEPURACION_UNIFICADO.md) |
| Modelo original y entorno | [ENTRENAMIENTO.md](ENTRENAMIENTO.md) |
| Modelo grande depurado de 128 tokens | [ENTRENAMIENTO_UNIFICADO.md](ENTRENAMIENTO_UNIFICADO.md) |
| Embeddings, conjuntos balanceados y longitud mínima | [RESULTADOS_BALANCEADOS.md](RESULTADOS_BALANCEADOS.md) |
| Tres proporciones políticas y tres semillas | [EXPERIMENTO_POLITICA_25.md](EXPERIMENTO_POLITICA_25.md) |
| Prueba nueva de afirmaciones cortas | [PRUEBA_EXTERNA_XFACT.md](PRUEBA_EXTERNA_XFACT.md) |
| Predicción individual o CSV con un checkpoint | [`probar_externo.py`](probar_externo.py) |

Este informe refleja el estado de los archivos locales en la fecha de corte. Los checkpoints y datos ignorados por Git necesitan copia y control de versiones de artefactos por separado si van a compartirse con otro equipo.

## 9. Archivos del modelo mejor ubicado y uso

El modelo que ocupa el **puesto 1 del ranking** es el pequeño mejorado con fastText CC español de 300 dimensiones, 192 tokens y semilla 42. Estos son sus archivos existentes:

| Función | Archivo |
| --- | --- |
| Script usado para entrenarlo | [`bilstm/preentrenados/entrenar.py`](preentrenados/entrenar.py) |
| Checkpoint entrenado, con pesos y vocabulario | [`datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt) |
| Configuración de ese entrenamiento | [`config.json`](../datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/config.json) |
| Script para predecir con el checkpoint | [`bilstm/probar_externo.py`](probar_externo.py) |

Desde la raíz de ScanTrue, para analizar una noticia con este modelo:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py \
  --modelo datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt \
  --referencia datasets/experimentos_balanceados/pequeno_mejorado \
  --texto 'Titular. Texto de la noticia...' --device cuda
```

`--modelo` selecciona el checkpoint correcto; sin esa opción, el script usa otro modelo por defecto. `--referencia` permite señalar posibles coincidencias con los datos de este entrenamiento. La salida incluye la predicción, `prob_falsa` y cuántos tokens se leyeron. Es una puntuación experimental, no una verificación de hechos.
