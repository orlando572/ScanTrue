# Plan de entrenamiento de mBERT para detección de noticias falsas en español

**Estado:** fases A–F completadas; la evaluación y sus límites están en [FASE_F_EVALUACION.md](FASE_F_EVALUACION.md). El candidato E1 de 256 tokens y `2e-5` se seleccionó solo con validación, pero falló en la prueba española externa y no está listo para despliegue. La prueba Polyglot queda como estrés con sesgo de fuente.  
**Fecha:** 7 de octubre de 2026.  
**Entorno comprobado:** Windows, RTX 5060 Laptop (8 GB), controlador 610.74, Python 3.14.7, PyTorch 2.13.0+cu130, Transformers 5.19.0, Datasets 5.1.0, Accelerate 1.15.0 y scikit-learn 1.9.1.

## 1. Objetivo y alcance

Entrenar `google-bert/bert-base-multilingual-cased` con una cabeza de **clasificación binaria de textos periodísticos**: `0 = REAL` y `1 = FALSA`. El uso final será sobre noticias en español. El inglés se usará como fuente adicional de entrenamiento y como experimento de transferencia entre idiomas. Se admitirán **únicamente ejemplos cuyo texto original esté en español o inglés**.

La predicción será una **señal de riesgo basada en el texto**, no una verificación factual concluyente: mBERT no consulta pruebas externas ni comprueba si un hecho ocurrió. Para la primera versión, la entrada será titular más cuerpo cuando ambos existan. No se mezclarán afirmaciones breves, artículos completos, sátira, publicaciones sociales y traducciones sin dejar explícita esa diferencia; si no se pueden armonizar, se separarán en experimentos o se excluirán.

**Hipótesis a contrastar:** el preentrenamiento multilingüe de mBERT puede transferir patrones aprendidos en inglés al español, pero la mejora no está garantizada. La comparación en un conjunto español nunca visto decidirá si añadir inglés ayuda. [Modelo mBERT](https://huggingface.co/google-bert/bert-base-multilingual-cased) · [Estudio de transferencia multilingüe](https://arxiv.org/abs/1904.09077) · [Estudio de detección multilingüe de noticias falsas](https://researchportal.ip-paris.fr/en/publications/multilingual-fake-news-detection-a-study-on-various-models-and-tr/).

## 2. Fase A: recopilación y auditoría de datasets

No se descargarán todos indiscriminadamente. Primero se registrarán procedencia, licencia, criterio de etiquetado, granularidad, campos, tamaño real, idioma, fechas, temas, fuentes, proporción por clase, duplicados y disponibilidad. La licencia del repositorio y los derechos sobre los artículos se revisarán por separado cuando corresponda.

| Prioridad | Dataset y uso propuesto | Ventaja | Riesgo / decisión pendiente |
| --- | --- | --- | --- |
| Alta | [Spanish Fake News Corpus v1](https://github.com/jpposadas/FakeNewsCorpusSpanish), español; candidato inicial de entrenamiento y validación. | 971 noticias, 491 reales y 480 falsas; titular, texto, tema, fuente y URL; licencia declarada CC BY 4.0. | Pequeño, de 2018. Respetar y auditar sus particiones publicadas antes de crear otras. |
| Alta | [Spanish Fake News Corpus v2 / FakeDeS 2021](https://github.com/jpposadas/FakeNewsCorpusSpanish), español; candidato a **prueba externa reservada**. | 572 casos de otro período; permite medir generalización fuera del corpus inicial. | Incluye 90 publicaciones sociales falsas. Evaluar por separado artículos y publicaciones; comprobar cruces con v1. |
| Media | [ISOT Fake News Dataset](https://onlineacademiccommunity.uvic.ca/isot/2022/11/27/fake-news-detection-datasets/), inglés; candidato para ampliar entrenamiento. | Titular y cuerpo; volumen considerable. | La clase real procede principalmente de Reuters y la falsa de otros sitios: alto riesgo de aprender la **fuente**, el estilo o el período en vez de la veracidad. No usar su puntuación interna como prueba principal. [Descripción de origen](https://onlineacademiccommunity.uvic.ca/isot/wp-content/uploads/sites/7295/2023/02/ISOT_Fake_News_Dataset_ReadMe.pdf). |
| Media | [PolyglotFakeFacts v2](https://data.mendeley.com/datasets/8yfrm6z9dx/1), **solo registros originales en inglés o español**; candidato complementario. | Titular, cuerpo, idioma, fecha, fuente y etiqueta; licencia CC BY 4.0. | El corpus completo tiene 18 idiomas y versiones traducidas al inglés: filtrar por idioma **original**, excluir los otros 16 y agrupar original/traducción de un mismo caso para impedir fuga. Auditar desequilibrio de fuente y tema. |
| Media | [Pérez-Rosas et al. (2018)](https://aclanthology.org/C18-1287/), inglés; prueba externa o experimento pequeño. | Artículos de varios temas con clases balanceadas. | Parte de los falsos fue escrita por participantes para el estudio; puede diferir de desinformación real. Verificar condiciones de uso del archivo original. |
| Condicional | [USMSC](https://huggingface.co/datasets/gabrielhuav/Unified-and-Balanced-Spanish-Fake-News-Corpus), español; explorar únicamente tras auditoría. | 61 674 registros unificados, con clase de sátira separada. | Solapa con Posadas-Durán; la sátira proviene de una sola fuente y la vista del CSV en Hugging Face actualmente informa un error de análisis. No incorporarlo sin revisar integridad, derechos y solapamiento. [Descripción de construcción](https://github.com/gabrielhuav/Spanish-Fake-News-Detection-Training). |

**Exclusiones iniciales:** [LIAR](https://arxiv.org/abs/1705.00648) reúne afirmaciones políticas breves, no noticias completas; [FakeNewsNet](https://github.com/KaiDMML/FakeNewsNet) publica de forma directa principalmente metadatos/titulares y advierte restricciones de redistribución del contenido completo. Podrán servir para otra tarea, pero no se mezclarán con artículos en esta primera versión.

**Entregable de la fase:** inventario de fuentes con URL y versión, licencia, checksum, número de registros útiles por idioma y clase, campos, porcentaje con cuerpo, criterio de etiqueta, incidencias y decisión de inclusión. Se conservará una copia inmutable de cada descarga y la cita requerida por sus autores.

## 3. Fase B: estandarización, unificación y control de calidad

1. Definir un esquema común: `id`, `dataset`, `version`, `idioma_original`, `titular`, `cuerpo`, `texto_modelo`, `etiqueta_original`, `etiqueta_binaria`, `tipo_texto`, `tema`, `fuente`, `url`, `fecha_publicacion`, `grupo_evento`, `split_origen` y `licencia`. Conservar el valor original de cada campo y un registro de cada transformación.
2. Mapear etiquetas solo cuando tengan significado equivalente: `REAL/TRUE -> 0`, `FAKE/FALSE -> 1`. Casos `MIXED`, `PARTLY TRUE`, `UNVERIFIED` y `SATIRE` quedarán fuera del binario inicial o en análisis separado. Nunca convertir automáticamente sátira en falsedad.
3. Verificar que el **texto de entrada** sea la noticia o su titular original, no el artículo del verificador que la desmiente: este último puede revelar la etiqueta. Eliminar del texto campos editoriales como «falso», marcas de verificación, URL, firma, rótulos de clase y plantillas de fuente cuando sean artefactos de recopilación. Conservar metadatos únicamente para auditoría y particionado.
4. Normalizar codificación Unicode, espacios, saltos de línea y HTML; retirar duplicados de encabezados y basura de extracción. Preservar mayúsculas, tildes, puntuación y contenido léxico: el modelo elegido es **cased**. No traducir, retrotraducir ni eliminar palabras frecuentes por defecto.
5. Medir vacíos, textos extremadamente cortos, idioma mal asignado, clases por fuente/tema/año, distribución de longitudes en palabras y tokens, porcentaje truncado y proporción español/inglés. Una muestra manual por corpus comprobará que texto y etiqueta se corresponden.
6. Deduplicar por URL normalizada, texto exacto y similitud aproximada; agrupar versiones del mismo hecho, titulares casi idénticos y pares verdadero/falso de un mismo evento. Revisar coincidencias entre todos los corpus, incluidas traducciones. No borrar automáticamente pares contrapuestos: agruparlos y resolver su posición en el particionado.
7. Si se usan archivos `.xlsx` del corpus español mediante Python, `pandas` necesitará **`openpyxl`**; es la única dependencia adicional prevista. Alternativa: exportarlos a CSV conservando tipos y acentos. La instalación se hará en la fase de ejecución, no en esta planificación.

**Puerta de calidad:** ningún registro sin texto utilizable, idioma confirmado o etiqueta justificable; tabla de exclusiones con motivo y recuentos antes/después. Revisar manualmente cualquier corpus cuyo idioma, origen o longitud prediga casi por sí solo la clase. La investigación sobre sesgos de dataset muestra que el rendimiento dentro de un corpus puede no mantenerse entre corpus. [Análisis de sesgo en evaluación](https://aclanthology.org/2026.eacl-srw.47/).

## 4. Fase C: particiones sin fuga de información

1. **Congelar primero la prueba española de otro período**: FakeDeS v2, solo artículos, después de resolver los cuatro pares de titulares v1/v2 detectados en la fase B. Sus 90 publicaciones sociales se reportarán aparte cuando puedan identificarse con fiabilidad; el campo de fuente no basta para clasificarlas automáticamente. Como v1 y v2 pertenecen a la misma familia de corpus, buscar además una prueba española de **otro origen**. El subconjunto español de PolyglotFakeFacts no sirve como prueba externa balanceada principal sin medidas adicionales: todos sus 480 ejemplos reales comparten fuente (`mundo.es`). Puede informarse como prueba de estrés separada, con esa limitación. Si no se encuentra un corpus independiente apto, declarar expresamente la limitación antes de los experimentos.
2. Mantener intactos los splits originales cuando sean apropiados. En los demás conjuntos, crear entrenamiento y validación con semilla fija, estratificando por clase e idioma cuando sea viable. Separar por `grupo_evento`, URL, fuente o período según el riesgo: ningún grupo de noticias repetidas o pares del mismo evento podrá cruzar particiones.
3. Aplicar detección de duplicados **entre entrenamiento, validación y prueba**, incluidas versiones en inglés y español. Si el mismo hecho aparece en varios corpus, excluirlo de una de las particiones. Documentar cuántos casos cambian por esta regla.
4. Mantener por separado: validación española para elegir hiperparámetros y umbral de los modelos que entrenan con español, validación inglesa para escoger el checkpoint del experimento de transferencia solo inglés, pruebas españolas reservadas para resultados finales y prueba inglesa externa como resultado secundario. El experimento solo inglés no usará etiquetas españolas ni para entrenar ni para elegir checkpoint. No ajustar nada observando las pruebas españolas.

## 5. Fase D: preparación del texto y línea base

- Tokenizador del mismo checkpoint `google-bert/bert-base-multilingual-cased`; entrada `titular + [SEP] + cuerpo` si ambos campos existen, y política explícita para registros sin cuerpo. Comparar, como ablación, **solo titular** frente a titular+cuerpo usando exactamente los mismos ejemplos.
- Longitud inicial `max_length=256`, truncamiento controlado y padding dinámico por lote. Medir qué porcentaje pierde texto y comparar **128, 192 y 256 tokens**; ensayar también **512** si la memoria lo permite y hay beneficio. El checkpoint tiene un máximo de 512 posiciones. [Configuración del modelo](https://huggingface.co/google-bert/bert-base-multilingual-cased/blob/main/config.json) · [Padding dinámico](https://huggingface.co/docs/transformers/main/data_collators).
- Antes del ajuste fino, establecer: predictor de clase mayoritaria y `TF-IDF + LogisticRegression` con la misma partición. Reportar tanto sus métricas como las de mBERT para saber si la complejidad adicional aporta valor.
- Guardar manifiestos de datos y particiones, checksums, semilla y versiones de librerías. Comprobar la API efectiva de Transformers 5.19.0 al implementar, sin asumir nombres de parámetros de versiones anteriores.

## 6. Fase E: experimentos de entrenamiento

Usar `AutoModelForSequenceClassification` con dos etiquetas y PyTorch/`Trainer`. E1, E2 y E3 comenzarán desde el mismo checkpoint base; E4 comenzará desde un checkpoint inglés de E2 previamente identificado. **No se entrenará ni publicará ningún modelo durante esta fase de planificación.** [Guía oficial de clasificación](https://huggingface.co/docs/transformers/tasks/sequence_classification) · [Trainer](https://huggingface.co/docs/transformers/main_classes/trainer).

### Aislamiento y conservación de cada entrenamiento

**Cada entrenamiento será una ejecución independiente y conservará todos sus resultados.** Se creará un identificador único que incluya experimento, longitud de tokens, semilla, fecha y un sufijo único. Antes de iniciar, el programa comprobará que la carpeta de destino no existe; si existe, **se detendrá** y exigirá un identificador nuevo. No se usarán rutas compartidas como `output/`, `checkpoint/` o `best_model/` para escribir resultados de distintas ejecuciones.

```text
mBERT/
  runs/
    E1_len128_seed42_YYYYMMDD-HHMMSS_<id>/
      config.json
      data_manifest.json
      checkpoints/
      best_model/
      metrics_validation.json
      metrics_test.json
      train_log.jsonl
    E1_len192_seed42_YYYYMMDD-HHMMSS_<id>/
    E1_len256_seed42_YYYYMMDD-HHMMSS_<id>/
    E1_len512_seed42_YYYYMMDD-HHMMSS_<id>/
```

La misma regla se aplicará a E0–E4, a cada combinación de hiperparámetros y a cada semilla. `output_dir`, directorio de logs, checkpoints, métricas y exportación del modelo apuntarán **dentro de la carpeta exclusiva de esa ejecución**. Se guardarán la configuración completa, hashes de datos/particiones, versiones, modelo base y métricas; un índice general solo referenciará rutas existentes y se actualizará sin tocar los artefactos de cada ejecución. No se eliminarán checkpoints ni ejecuciones anteriores automáticamente. Si una ejecución falla, se conservará su carpeta y el siguiente intento usará un ID nuevo; una reanudación explícita quedará registrada como tal.

En E4, el ajuste en español partirá de una **copia o lectura** del checkpoint inglés elegido, escribirá en una carpeta nueva y registrará la ruta exacta del entrenamiento padre. Nunca continuará escribiendo en la carpeta de E2. Una vez finalizada una ejecución, sus archivos se tratarán como inmutables; cualquier evaluación adicional tendrá un archivo nuevo con ID propio, sin reemplazar métricas previas.

| Experimento | Entrenamiento | Pregunta que responde |
| --- | --- | --- |
| E0 | Línea base de clase mayoritaria y TF-IDF | ¿Cuánto aporta mBERT? |
| E1 | Solo artículos en español | Referencia principal para el objetivo español. |
| E2 | Solo artículos en inglés | ¿Hay transferencia inglés→español sin etiquetas españolas? |
| E3 | Español + inglés, con proporción controlada | ¿Mejora o perjudica añadir inglés? |
| E4 | Inglés seguido de ajuste adicional con español | ¿Es mejor la adaptación secuencial que la mezcla? |

Configuración inicial para una RTX 5060 Laptop de 8 GB: secuencia de 256 tokens; `per_device_train_batch_size` de 4, `gradient_accumulation_steps` de 4 (lote efectivo 16), 3 épocas, tasa de aprendizaje inicial `2e-5`, `weight_decay=0.01`, calentamiento del 10 % y evaluación cada época. Son **puntos de partida**, no valores óptimos demostrados. Usar precisión mixta `bf16` si la ejecución la admite; si no, probar `fp16`. Registrar memoria máxima, duración y errores de memoria. Ajustar tamaño de lote o longitud antes de cambiar otros factores. [Acumulación de gradientes](https://huggingface.co/docs/transformers/grad_accumulation).

Escoger checkpoint con **F1 de la clase FALSA en la validación española** para E1, E3 y E4, sujeto a revisar también precisión, recall y F1 macro; para E2 usar exclusivamente validación inglesa. Hacer una búsqueda pequeña y justificada de tasa (`1e-5`, `2e-5`, `3e-5`), longitud (**128/192/256 y 512 si cabe**) y mezcla inglés/español; detener el barrido cuando el coste deje de justificarlo. Ejecutar los candidatos principales con al menos tres semillas si el tiempo de GPU lo permite y reportar media y dispersión. Si hay desbalance, comparar muestreo controlado o pesos de clase **solo en entrenamiento**.

## 7. Fase F: pruebas, métricas y criterio de selección

**Métrica principal:** F1 de la clase `FALSA` en la prueba española reservada de FakeDeS v2, calculada una sola vez tras fijar modelo y umbral. La prueba española de otro origen, si está disponible, medirá generalización entre corpus y se reportará sin mezclarla con la principal. La configuración ganadora se decidirá con **validación**, antes de abrir cualquiera de las pruebas; las configuraciones E1–E4 predefinidas podrán evaluarse una vez en las pruebas para comparación, sin otra ronda de ajustes. Mostrar además:

- Precisión y recall de `FALSA`; F1, precisión y recall **por cada clase**; F1 macro; exactitud y exactitud balanceada.
- Matriz de confusión con FP (noticia real marcada falsa) y FN (noticia falsa marcada real). Indicar el soporte de cada clase y el umbral de decisión.
- Curva precisión-recall y **average precision** cuando se disponga de probabilidades; calibración/Brier como diagnóstico si se van a mostrar probabilidades al usuario. Ajustar cualquier umbral o calibración solo con validación española.
- Resultados separados por idioma, dataset, tema, fuente conocida/desconocida, período, longitud y tipo de texto. Reportar desempeño en corpus externo, no solo en una división aleatoria del mismo corpus.
- Intervalos de confianza mediante remuestreo por **grupo de evento o fuente**, evitando tratar textos relacionados como independientes. Comparar E1/E2/E3/E4 sobre el **mismo** conjunto español y analizar ejemplos de error y patrones de fuga.

El criterio para incorporar inglés será una mejora reproducible de F1 en **validación española**, sin caída inaceptable de precisión o recall según el uso previsto, y su confirmación en las pruebas reservadas. Si las pruebas contradicen la validación, se informará como limitación y se requerirá un nuevo conjunto de prueba antes de rediseñar el modelo. No se fijará un umbral numérico arbitrario antes de observar tamaño y calidad de los datos. [Definición de F1 macro/binario en scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html) · [Seguimiento del mejor checkpoint](https://huggingface.co/docs/transformers/main_classes/trainer).

## 8. Entregables y orden de ejecución futuro

1. Inventario y auditoría de corpus, con decisión de inclusión y derechos de uso.
2. Datos normalizados con manifiesto, trazabilidad al original y reporte de calidad.
3. Particiones congeladas y prueba automática de que no hay cruces de ejemplos/grupos.
4. Línea base y configuraciones E1–E4 con registro de experimentos, semillas, métricas y uso de GPU.
5. Informe final con comparación y análisis de errores; checkpoint elegido y tarjeta del modelo que explique datos, límites y uso previsto.

**Primer paso al ejecutar el plan:** auditar Spanish Fake News Corpus v1/v2 y elegir la prueba española externa antes de descargar o mezclar los corpus ingleses. Esta decisión protege la evaluación principal de contaminación accidental.
