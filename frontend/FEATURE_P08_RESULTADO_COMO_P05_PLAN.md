# Feature P08: resultado guardado con el diseño de P05

## Estado y alcance

Feature implementado en el frontend. Afecta la presentación del resultado unificado en P08 y reutiliza el indicador visual de P05. No requiere cambios en el backend ni modifica la consulta, el historial o la eliminación.

Este plan actualiza únicamente la sección de resultado descrita en `PANTALLA_P08_DETALLE_HISTORIAL_PLAN.md`. El diseño de referencia es el panel actual de P05, definido en `FEATURE_P05_INDICADOR_CINCO_NIVELES_PLAN.md`.

## Objetivo

Al abrir un análisis anterior, mostrar su porcentaje unificado con la misma composición de P05: anillo con cifra a la izquierda, etiqueta del nivel a la derecha y la carita correspondiente debajo de la etiqueta. P08 seguirá indicando claramente que se trata del análisis guardado mediante su título, fecha y texto.

## Datos y regla visual

- Usar únicamente `resultado_unificado.probabilidad_falsa` del detalle guardado. No volver a ejecutar los modelos ni promediar sus salidas individuales en el popup.
- Reutilizar la función de presentación de P05 para obtener el porcentaje entero visible, nivel, tono e icono. Los cinco rangos son 0–20, 21–40, 41–60, 61–80 y 81–100 %.
- Usar exactamente los mismos colores, grosor del anillo, tamaños, espaciado, etiquetas y caritas de P05. Una modificación futura del indicador deberá reflejarse en ambas pantallas.
- Retirar del panel actual de P08 **Salida para falsa** y la frase sobre cuántos modelos participaron. El panel mostrará solamente anillo, porcentaje, etiqueta y carita, como P05.
- Mantener fuera del panel la acción **Ver desglose por modelo** cuando existan salidas individuales guardadas; seguirá abriendo P06 con ese registro.

## Estados

| Situación | Presentación en P08 |
| --- | --- |
| Probabilidad unificada válida | Mismo indicador de P05 y nivel correspondiente al entero visible. |
| 0 % o 100 % | Mostrar el extremo exacto, con cifra y etiqueta legibles. |
| Un solo modelo usado en el análisis guardado | Mostrar el unificado recibido, sin leyenda adicional dentro del panel. |
| Resultado unificado ausente o inválido | Panel vacío de resultado, sin anillo activo, cifra, etiqueta ni carita inventados; mostrar **Resultado unificado no disponible**. |
| Salidas individuales disponibles sin unificado | Conservar **Ver desglose por modelo** aunque el panel unificado no tenga cifra. |

El texto, fecha, dominio, estados de carga y error, regreso a P07 y confirmación de eliminación conservan su comportamiento.

## Pasos de implementación

1. Extraer del componente de P05 el panel del anillo, la etiqueta y la carita a un componente React compartido. Mantener su SVG y estilos actuales, sin añadir una librería de gráficos.
2. Hacer que P05 use el componente compartido y comprobar que su apariencia y comportamiento no cambian.
3. Presentar el resultado guardado de P08 con la misma función de nivel y montar allí el componente compartido. Eliminar la cifra roja y los textos actuales de ese panel.
4. Ajustar la separación vertical del detalle para que el texto analizado, indicador, acceso a P06 y eliminación sigan legibles en el popup de 400 px, sin desplazamiento horizontal.
5. Verificar resultados válidos, los límites de los cinco rangos, porcentajes ausentes y registros con una sola salida individual. Comprobar P05 y P08 en Chrome, ejecutar pruebas y compilar el frontend.

El indicador compartido, su uso en P05 y P08 y la presentación del resultado guardado están implementados. Pasan las 50 pruebas y la compilación del frontend. La revisión visual interactiva en Chrome queda pendiente.

## Criterios de aceptación

- Para el mismo porcentaje unificado, P05 y P08 muestran el mismo anillo, cifra, color, etiqueta y carita.
- Un análisis anterior de 78 % muestra **Probablemente falso**, anillo anaranjado y carita triste, sin **Salida para falsa** ni texto sobre el número de modelos en el panel.
- P08 usa el resultado guardado; abrir el detalle no inicia otro análisis ni cambia el valor mostrado.
- Un registro sin resultado unificado válido no recibe un porcentaje calculado a partir de los modelos individuales.
- Siguen funcionando el desglose P06, el regreso al historial y la eliminación confirmada.
