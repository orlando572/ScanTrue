# Plan de mejora del detector de noticias falsas en español

Trabajaremos un paso a la vez. Cada cambio tendrá una hipótesis, un resultado
medido y una decisión registrada aquí. El modelo de referencia es el BiLSTM
`sin_politica` entrenado con `bilstm/entrenar.py`.

## Referencia actual

| Dato | Valor |
| --- | ---: |
| Entrenamiento | 1834 noticias |
| Validación | 294 noticias |
| Prueba usada hasta ahora | 807 noticias |
| Mejor época | 20 de 25 ejecutadas |
| F1 macro en validación | 64,96 % |
| F1 para «falsa» en validación | 65,55 % |
| F1 macro en prueba | 61,45 % |
| F1 macro de FakeDeS | 55,66 % |

La pérdida de entrenamiento llegó casi a cero, mientras las métricas de
validación permanecieron alrededor del 65 %. Es una señal de posible
sobreajuste. Además, el mismo conjunto de prueba ya influyó en la elección de
la variante sin política; no debe usarse repetidamente para escoger nuevos
hiperparámetros. Para una estimación final necesitaremos una fuente externa
nueva o un conjunto reservado que no se haya consultado durante el desarrollo.

## Paso 1. Auditar errores y longitud de las noticias — auditoría cuantitativa terminada

**Pregunta:** ¿qué errores se concentran en noticias largas y qué patrones
podemos revisar manualmente?

El script `bilstm/analizar_errores.py` carga el modelo entrenado y genera
`datasets/modelos_bilstm/sin_politica/auditoria_validacion.csv` y su resumen
JSON. No cambia el modelo. En validación detectó **103 errores**: 43 noticias
falsas clasificadas como reales y 60 reales clasificadas como falsas. De 294
noticias, **259 (88,1 %) exceden los 192 tokens** que puede leer el modelo.
En la prueba, un recuento de longitudes previo encontró **85,1 %** de textos
por encima de ese límite. Estas cifras justifican comparar más contexto; no
demuestran por sí solas que aumentarlo mejore el F1.

En **72 de los 103 errores** la probabilidad asignada a la clase predicha fue
al menos 0,90. Esa probabilidad no está calibrada como certeza factual;
revisaremos esos casos antes de considerar un umbral de confianza en una
aplicación.

La comparación por longitud encontró 20 % de errores entre las 35 noticias de
hasta 192 tokens, 34 % entre las 144 de 193 a 384 y más de 40 % en las de
385 a 512. Los grupos tienen tamaños y proporciones de clases distintos; esta
asociación no prueba causalidad. La revisión de etiquetas y de una muestra
de textos completos de ambas clases sigue pendiente y formará parte de la
depuración de datos del paso 3. No se cambiaron etiquetas.

## Paso 2. Comparar la longitud de entrada — completado en validación

**Hipótesis:** leer más del cuerpo de la noticia mejora la validación.

Se entrenó la misma arquitectura con límites de **192, 384 y 512 tokens** y
semillas **42, 43 y 44**, manteniendo el lote de 32, las demás opciones y las
particiones. Los nueve entrenamientos usaron GPU y el modo `--validation-only`:
no leyeron ni evaluaron la partición de prueba. Sus configuraciones, modelos,
historiales y métricas están en `datasets/experimentos_longitud/`.

| Máximo de tokens | F1 macro semillas 42 / 43 / 44 | Media ± desviación | Recall «falsa» medio |
| --- | --- | ---: | ---: |
| 192 | 64,96 / 65,98 / 62,85 % | 64,60 ± 1,59 % | 65,96 % |
| 384 | 70,03 / 68,26 / 66,90 % | 68,40 ± 1,57 % | 66,19 % |
| 512 | 70,41 / 69,03 / 68,53 % | **69,32 ± 0,97 %** | **68,56 %** |

Con semilla 42, al pasar de 192 a 512 tokens se corrigieron 50 errores de
validación y aparecieron 34 nuevos: mejora neta de 16 noticias. Entre las 48
noticias de 385 a 512 tokens hubo 15 correcciones y 3 nuevos errores. El F1
macro pasó de 64,96 % a 70,41 % con esa semilla. Aun con 512 tokens, 67 de
294 noticias de validación siguen recortadas.

**Decisión:** usar 512 tokens como candidato para el siguiente entrenamiento.
Superó a 192 y 384 en las tres semillas sin reducir el recall medio de la
clase falsa. Mantener el modelo de 192 tokens como referencia hasta evaluar
el candidato en una fuente externa nueva. No se sustituyeron sus pesos ni se
usó la prueba actual para escoger longitud.

**Contraejemplo externo conocido:** una captura que afirmaba que el MINSA
había eliminado el teletrabajo fue [verificada como falsa por Red Ama Llulla](https://elbuho.pe/2026/08/es-falsa-la-version-de-que-el-ministro-de-salud-elimino-la-modalidad-de-teletrabajo-en-el-minsa/).
Con el mismo texto de 56 tokens, el modelo de 192 predijo «falsa»
(`prob_falsa=0,9947`) y el de 512 predijo «real» (`prob_falsa=0,0004`).
Ninguno recortó esta entrada. Por tanto, **la mejora media en validación no
garantiza una mejora en noticias recientes**. El caso queda en
`datasets/evaluaciones_externas/casos_diagnostico.csv` para analizar errores;
ya fue visto durante el desarrollo y **no debe contarse como prueba externa
intacta** ni añadirse automáticamente al entrenamiento.

El criterio de mejora consistente en validación se cumplió. Falta comprobar
generalización entre fuentes y latencia antes de promover este candidato.

## Paso 3. Ampliar y depurar los datos españoles

Buscar noticias reales y falsas de salud, ciencia, economía, tecnología y
otros temas, con fuentes y fechas diversas. Revisar licencias y significado de
las etiquetas antes de incorporarlas. Eliminar duplicados y noticias casi
idénticas entre particiones. Registrar el aporte por fuente y mantener una
evaluación externa separada. La calidad y diversidad de los datos tienen
prioridad sobre añadir más noticias de un único tema.

## Paso 4. Reducir sobreajuste

Comparar, **un cambio por vez**, dropout, peso de regularización, tamaño de
embeddings y parada temprana. Repetir con varias semillas y registrar medias
y variación, porque una sola ejecución puede ser engañosa. Conservar cambios
solo cuando la validación mejore de forma consistente.

## Paso 5. Comparar modelos

Entrenar una referencia sencilla con TF-IDF y regresión logística; después,
comparar el BiLSTM con un modelo de lenguaje preentrenado para español o mBERT.
Usar las mismas particiones y métricas. La comparación decidirá si conviene
seguir invirtiendo en el BiLSTM o pasar a otro modelo.

## Antes de cualquier despliegue

Obtener una evaluación en noticias externas no usadas para elegir el modelo;
medir F1 macro, precisión y recall de «falsa», falsos positivos, resultados
por fuente y tema, y tiempo de inferencia. Crear la interfaz de predicción y
probarla con entradas reales. Un clasificador de texto puede aprender señales
de redacción y procedencia, pero su predicción no sustituye la verificación de
hechos con evidencia. El formato del nuevo conjunto y los comandos de
evaluación están en `bilstm/PRUEBA_EXTERNA.md`.

El contraejemplo del MINSA muestra una necesidad adicional: para afirmaciones
sobre decisiones recientes, estudiar una etapa de búsqueda de fuentes
oficiales y contraste de la afirmación. Más tokens del mismo mensaje no
aportan por sí solos esa evidencia externa.

## Registro de decisiones

| Fecha | Paso | Resultado | Decisión |
| --- | --- | --- | --- |
| 2026-10-06 | Referencia | F1 macro validación 64,96 %; prueba 61,45 % | Conservar pesos y configuración como referencia |
| 2026-10-06 | Auditoría inicial | 259/294 noticias de validación exceden 192 tokens; 103 errores | Probar 384 y 512 tokens en el paso 2 |
| 2026-10-06 | Longitud, 3 semillas | F1 macro medio: 64,60 % (192), 68,40 % (384), 69,32 % (512) | 512 tokens es candidato; falta prueba externa nueva |
| 2026-10-06 | Caso MINSA verificado | 512 falló con alta puntuación para «real»; 192 acertó | Registrar fallo; no promover 512 por la validación sola |

## Comandos útiles

```bash
bilstm/.venv/bin/python bilstm/analizar_errores.py
bilstm/.venv/bin/python bilstm/entrenar.py --help
bilstm/.venv/bin/python bilstm/entrenar.py --validation-only --max-len 512 --seed 42 --output datasets/experimentos_longitud/t512_s42
```

Los CSV de auditoría y los modelos viven bajo `datasets/` y están ignorados
por Git. Los scripts y este plan sí pueden compartirse con el equipo.
