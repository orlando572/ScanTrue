# Plan pendiente: limpieza conservadora del texto de noticias

**Estado:** implementado localmente en el backend; no se han modificado datos
históricos ni aplicado migraciones. Este documento conserva el diseño y los
criterios de verificación.

## Objetivo

Convertir texto seleccionado o pegado desde páginas de noticias en una entrada
plana y estable para BiLSTM y mBERT. Quitar artefactos de presentación sin
reescribir el contenido ni intentar verificar los hechos. La limpieza debe ser
determinista e idempotente: limpiar dos veces debe producir el mismo resultado
que limpiar una vez.

## Entrada y salida esperadas

Ejemplo abreviado de entrada:

```text
PNP captura a alias “Leo”

##### Durante operativo realizado en Madre de Dios se incautaron 22 granadas.

**10/10/2026 20:37&#x20;**&#x45;n concordancia con la estrategia


&#x20;impulsada por el Ministerio del Interior, la PNP logró la captura.
```

Salida para análisis:

```text
PNP captura a alias “Leo” Durante operativo realizado en Madre de Dios se incautaron 22 granadas. 10/10/2026 20:37 En concordancia con la estrategia impulsada por el Ministerio del Interior, la PNP logró la captura.
```

El título, subtítulo, fecha, nombres, cifras y orden de las frases permanecen.
La salida es una sola cadena, igual al formato prácticamente plano usado en
los CSV de entrenamiento.

## Reglas implementadas, en este orden

1. Decodificar entidades HTML terminadas en `;` con una función estándar hasta
   que el resultado sea estable. Esto convierte `&#x20;`, `&#x45;`, `&nbsp;` e
   incluso entidades anidadas, pero conserva un `&` normal. No tratar la
   entrada como HTML de una página completa ni borrar texto entre `<` y `>`.
2. Normalizar Unicode con NFKC, como en la preparación del corpus BiLSTM.
   Convertir espacios no separables a espacios normales y retirar caracteres
   invisibles de formato solo cuando no tengan valor lingüístico. No corregir
   letras dañadas (`�`) ni traducir o cambiar palabras.
3. Quitar únicamente marcas Markdown reconocibles: prefijos `#` de encabezado
   al inicio de una línea y delimitadores dobles de negrita (`**` o `__`).
   Conservar siempre el texto dentro de esas marcas. Los delimitadores simples
   (`*` o `_`) se mantienen: el corpus entrenado contiene marcadores como
   `*NUMBER*` y `*URL*`, que no deben reescribirse para mBERT.
4. Sustituir secuencias de espacios, tabulaciones y saltos de línea por un
   único espacio; quitar espacios de los extremos. No eliminar frases, fechas,
   subtítulos, citas, nombres propios ni cantidades.
5. Si el resultado queda vacío o sin palabras suficientes, conservar los
   errores `422` actuales. Contar tokens **después** de limpiar.

La primera versión no intentará detectar publicidad, navegación, comentarios,
texto repetido o un titular a partir de la primera línea. Son decisiones de
extracción de contenido distintas y podrían borrar información válida.

## Integración en el backend

- Crear una función pura, por ejemplo `clean_news_text`, en
  `backend/services/text_cleaning.py`, sin dependencias de red ni de los
  modelos.
- Llamarla al comienzo de `AnalysisService.analyze`, antes de comprobar texto
  vacío, validar los 100 tokens y aplicar los límites de mBERT/BiLSTM.
- El titular seleccionado ya forma parte de `texto`; no existe un campo
  separado que requiera limpieza o comparación.
- Enviar el mismo texto limpio a ambos modelos. El recorte actual de mBERT
  determina el fragmento compartido cuando su tokenizador está disponible;
  BiLSTM puede leer menos tokens según su propio límite.
- Conservar la regla actual de persistencia: `outcome.text` es el fragmento
  efectivamente analizado; ese mismo valor se guarda en el historial y se usa
  para `hash_texto` y el registro blockchain. No volver a limpiar en la ruta,
  el repositorio o el frontend. Los análisis históricos no se recalculan.

No se necesita una migración de Supabase para esta limpieza: los campos
`texto` y `hash_texto` existentes ya almacenan el fragmento analizado.

## Verificación

1. Pruebas de la función con el ejemplo anterior, entidades decimales y
   hexadecimales, espacios Unicode, encabezados, negritas, entrada ya limpia,
   cadenas vacías y texto con símbolos legítimos.
2. Comprobar idempotencia y que no desaparezcan nombres, números o negaciones.
   Probar una selección con titular incorporado, sin duplicarlo.
3. Prueba del servicio: validación de 100 tokens después de limpiar, recorte,
   igualdad del texto enviado a ambos modelos y `outcome.text` esperado.
4. Prueba de ruta/persistencia: el texto guardado y su SHA-256 corresponden al
   fragmento limpio y recortado, no a la selección original. Confirmar que el
   historial antiguo sigue legible.
5. Comparar una muestra de noticias reales y del corpus preparado antes y
   después: texto, longitud, tokens, recorte y predicciones. Revisar
   manualmente cualquier pérdida de contenido o cambio de clasificación; no
   asumir que limpiar mejora la precisión del modelo. Los textos ya planos
   deberían quedar iguales salvo normalizaciones Unicode justificadas.

## Criterios de aceptación

- El ejemplo produce la salida documentada; `&#x45;n` pasa a `En`.
- Una noticia ya limpia no cambia y la función es idempotente.
- Los dos modelos reciben la misma cadena preparada; los límites de tokens se
  aplican después de limpiar.
- Historial, hash y blockchain se refieren exactamente al fragmento analizado.
- Ningún dato histórico se altera y no se requiere un cambio de esquema.

## Verificación local realizada

- Las pruebas de limpieza, servicio y ruta pasan con el entorno del backend.
  Cubren el ejemplo, entidades anidadas, marcadores del corpus, titular
  incorporado una vez, mínimo de tokens y hash del texto guardado.
- La limpieza se comparó con las 3.066 filas de entrenamiento de
  `pequeno_mejorado`: 3.043 permanecieron idénticas y 23 cambiaron,
  principalmente por caracteres de espacio invisible. Ninguna fila dejó de
  ser idempotente. No se infiere de ello una mejora de precisión.
- Una prueba local con un texto de noticia que contenía encabezado Markdown,
  entidad HTML y espacios repetidos completó la inferencia real de BiLSTM y
  mBERT (`estado=ok` para ambos, 169 y 267 tokens respectivamente). El texto
  analizado coincidió con la salida de la función de limpieza.
