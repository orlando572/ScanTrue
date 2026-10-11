# Feature P07: navegación y cinco niveles en el historial

## Estado y alcance

Feature implementado en el frontend. Solo afecta la presentación de P07 dentro del popup y sus pruebas. No requiere cambios en el backend. Este documento actualiza las decisiones sobre la cabecera y el resultado de cada fila de `PANTALLA_P07_HISTORIAL_PLAN.md`; el resto del comportamiento de P07 se conserva.

## Objetivo

Hacer más compacta la navegación del historial y dar color a cada porcentaje con la misma escala de cinco niveles que ya aparece en P05 y P06. Las etiquetas de nivel se retiraron de las filas por decisión posterior.

## Cabecera

- Quitar de P07 el botón independiente con icono y texto **Volver**.
- Colocar un botón con icono de flecha inmediatamente a la izquierda del título **Historial de análisis**, alineados en una sola cabecera.
- El botón regresa a la pantalla desde la que se abrió P07. Debe tener un nombre accesible, por ejemplo **Volver**, además de foco visible y un área cómoda para pulsarlo.
- Mantener la cabecera accesible mientras se recorre un historial largo dentro del popup.

## Resultado en cada fila

Usar `resultado_unificado.probabilidad_falsa` ya guardado en cada análisis. Convertirlo al porcentaje entero visible con la misma regla de redondeo y clasificación de P05 y P06. No volver a analizar el texto ni calcular otro resultado.

| Porcentaje visible | Nivel usado para el color y la accesibilidad | Color del porcentaje |
| --- | --- | --- |
| 0–20 % | Muy probablemente verdadero | Verde profundo `#246B61` |
| 21–40 % | Probablemente verdadero | Verde `#39784D` |
| 41–60 % | Resultado incierto | Ámbar `#8B5A12` |
| 61–80 % | Probablemente falso | Anaranjado `#AE5819` |
| 81–100 % | Muy probablemente falso | Rojo `#A3342B` |

En la fila se muestra únicamente el porcentaje, sin comentario encima. El nivel permanece en el nombre accesible del porcentaje para que el color no sea la única forma de interpretarlo. Si falta un porcentaje válido, mostrar **Resultado no disponible**, sin porcentaje ni color de resultado inventados.

## Jerarquía y espacio

- Mostrar el porcentaje sin comentario encima y reducir la columna de resultado para dar más espacio a la vista previa.
- Aumentar el porcentaje ligeramente, de 20 px a aproximadamente 24 px, con cifras alineadas y sin convertirlo en el elemento dominante de toda la fila.
- Conservar legibles la fecha y la vista previa del texto; evitar recortes y desplazamiento horizontal en el popup.
- Mantener la fila completa como acceso al detalle P08.

## Pasos de implementación

1. Hacer que el botón general **Volver** no aparezca en P07 y pasar a la pantalla del historial la misma acción de regreso que usa el popup.
2. Construir la cabecera de P07 con botón de flecha a la izquierda del título y sus estados de teclado y foco.
3. Reutilizar la función común de cinco niveles para la probabilidad unificada de cada registro y obtener su comentario y tono a partir del porcentaje visible.
4. Ajustar la fila y sus estilos para el nuevo tamaño y color del porcentaje y para comentarios largos.
5. Verificar navegación, resultados ausentes, límites entre niveles y legibilidad en el ancho real del popup. Ejecutar las pruebas y la compilación del frontend.

Los cambios de código están implementados. Las 49 pruebas del frontend y la compilación pasan. La revisión visual interactiva en Chrome con un historial real queda pendiente.

## Criterios de aceptación

- En P07 no aparece un control separado con el texto **Volver**; la flecha se encuentra a la izquierda de **Historial de análisis** y regresa correctamente.
- Ninguna fila con porcentaje válido muestra **Salida para falsa** ni comentarios de nivel encima de la cifra. El color corresponde al mismo entero visible que se usa en P05 y P06.
- Los límites 0, 20, 21, 40, 41, 60, 61, 80, 81 y 100 % presentan los cinco niveles sin huecos ni contradicciones. Los decimales cercanos a un límite siguen la regla de redondeo común.
- El porcentaje es ligeramente mayor que antes y la vista previa conserva espacio suficiente sin desplazamiento horizontal.
- Los registros sin resultado válido siguen mostrando **Resultado no disponible**. La carga, paginación, apertura de P08 y estados vacío o de error siguen funcionando.
