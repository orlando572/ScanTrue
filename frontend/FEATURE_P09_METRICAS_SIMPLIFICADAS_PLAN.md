# Feature P09: pruebas del modelo en lenguaje claro

## Estado y alcance

Feature implementado en el frontend. Solo cambia la presentación de P09 dentro del popup y las pruebas. La consulta a `GET /metricas` y los datos del backend permanecen intactos. Este plan actualiza el contenido y la jerarquía de `PANTALLA_P09_METRICAS_PLAN.md`.

## Objetivo

Que una persona pueda entender rápidamente cómo le fue al modelo en sus pruebas, sin recorrer nombres de medidas técnicas ni una ficha extensa. Las cifras corresponden a pruebas del modelo, no al análisis de la noticia abierta.

## Nombres y contenido propuestos

| Elemento actual | Presentación propuesta |
| --- | --- |
| **Métricas de evaluación** | **Pruebas del modelo**. También actualizar el nombre accesible del icono que abre P09. |
| Nombre del modelo y línea de versión | **BiLSTM** o el nombre recibido, en una sola línea discreta. Omitir la versión de la vista principal. |
| Nombre técnico del `conjunto` | Nombre breve y claro únicamente si hay una equivalencia confirmada para ese valor. Si no, conservar el nombre recibido sin inventar otro conjunto. |
| `n` ejemplos | **1.200 textos evaluados**, cuando exista. |
| **Exactitud** | **Aciertos en las pruebas**, acompañado del porcentaje válido de `exactitud`. |
| **F1 macro** y **Ver más medidas** | Retirarlos de la pantalla simplificada junto con precisión, cobertura y F1 por clase. No sustituirlos por una cifra calculada ni llamar «aciertos» a F1. |
| **Fuente: [texto largo]** | **Datos: [nombre breve]**. Una dirección web se muestra con su dominio. Para otros nombres se conserva el texto recibido. Cuando el origen es largo o se abrevia, se puede desplegar el valor completo. |
| **Limitaciones** | **Sobre estas pruebas**, en un apartado desplegable que conserva el contenido recibido. |

Quitar la frase **Evaluaciones publicadas del modelo.**, que repite la función del nuevo título. No mostrar la versión, medidas avanzadas, matriz de confusión ni datos sin una explicación útil para el usuario. Si falta `exactitud`, omitir su cifra; no presentar F1 como reemplazo de aciertos.

## Jerarquía y tamaño

1. Cabecera compacta con flecha y título **Pruebas del modelo**.
2. Nombre del modelo como referencia secundaria.
3. Una ficha compacta por conjunto: nombre, porcentaje de aciertos como cifra principal, número de textos evaluados y origen breve si están disponibles.
4. Apartado desplegable **Sobre estas pruebas** solo cuando la API entregue limitaciones.

Reducir el tamaño de las cifras de 24 px a aproximadamente 21–22 px y compactar márgenes y rellenos de las fichas. Mantener el texto legible y las cifras alineadas, con espacio suficiente para varios conjuntos sin desplazamiento horizontal. El origen tendrá una sola línea visible; su valor completo seguirá disponible mediante un nombre accesible o control de consulta si se abrevia.

## Tratamiento seguro de los nombres de origen

La API local no estuvo accesible desde este entorno durante la implementación, por lo que no se crearon equivalencias de nombres no verificadas. Las direcciones web se abrevian a su dominio y los demás valores conservan su nombre recibido. Los orígenes largos o abreviados se pueden desplegar para leer el valor original. Los nombres y porcentajes proceden del mismo registro de evaluación recibido.

## Estados

- **Carga y error:** conservar mensajes breves y **Intentar de nuevo**.
- **Sin evaluaciones:** mostrar **Aún no hay pruebas disponibles**.
- **Sin aciertos válidos:** mantener el conjunto y sus otros datos presentes, sin inventar un porcentaje.
- **Sin número de textos, origen o limitaciones:** omitir el dato ausente y conservar la alineación de la ficha.
- **Varios conjuntos:** repetir la misma estructura compacta y permitir desplazamiento dentro del popup.

## Pasos de implementación

1. Confirmar los valores de `fuente`, `conjunto` y `limitaciones` disponibles para decidir abreviaturas fieles a los datos.
2. Ajustar el presentador de métricas con nombres breves verificados y solo los datos que usará la vista; conservar la validación de porcentajes.
3. Cambiar título, etiquetas y composición de P09. Quitar el desplegable de medidas avanzadas, la versión visible y el texto repetido.
4. Compactar tipografía y espacios en los estilos del popup, sin alterar otras pantallas.
5. Verificar datos ausentes, cero válido, varios conjuntos, origen largo, teclado y tamaño real de Chrome. Ejecutar pruebas y compilación del frontend.

La vista simplificada está implementada. Pasan las 51 pruebas y la compilación del frontend. La revisión visual interactiva en Chrome y la comprobación de nombres reales de origen y limitaciones quedan pendientes.

## Criterios de aceptación

- P09 se llama **Pruebas del modelo** y muestra una cifra de **Aciertos en las pruebas** solo cuando `exactitud` sea válida.
- La pantalla no muestra F1, precisión, cobertura ni versión como contenido principal, y no recalcula ni inventa resultados.
- El origen usa **Datos** y un nombre visualmente breve, sin perder la posibilidad de consultar su valor original.
- Las fichas son más compactas que las actuales y siguen siendo legibles dentro del popup.
- Carga, errores, conjuntos múltiples y ausencia de datos continúan funcionando; ningún cambio requiere modificar el backend.
