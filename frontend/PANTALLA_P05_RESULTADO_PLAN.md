# P05 Resultado del análisis

## Estado de este archivo

Pantalla implementada en el popup según esta planificación. La imagen siguiente usa **73 %** y dos modelos coincidentes solo para mostrar la composición; la pantalla real utiliza los valores recibidos.

![Concepto visual de P05](referencias/p05-concepto-v2.png)

## Objetivo de P05

Presentar de forma clara el resultado unificado del análisis, indicar cuántos modelos participaron y mostrar si sus salidas coinciden o discrepan cuando la API lo informe. Facilitar el acceso al desglose.

## Datos que recibe

| Dato de la respuesta | Uso en P05 |
| --- | --- |
| `resultado_unificado.probabilidad_falsa` | Porcentaje principal con la etiqueta **Salida para falsa**. |
| `resultado_unificado.modelos_utilizados` | Indicar si el resultado combina dos modelos o procede de uno solo. |
| `comparacion` | Mostrar coincidencia o discrepancia junto al porcentaje solo cuando haya comparación real. |
| `resultados` | Conservarlos para abrir P06; los valores individuales se detallan allí. |

El porcentaje es la probabilidad recibida multiplicada por 100 para presentación y redondeada con un criterio visual consistente. P05 no calcula pesos, clases, niveles de riesgo ni un resultado unificado propio. Los campos exactos deben comprobarse con la API vigente antes de la integración.

## Contenido y jerarquía

1. Cabecera común de ScanTrue con accesos a Historial y Cuenta.
2. Título **Resultado del análisis**.
3. Un solo panel destacado: etiqueta **Salida para falsa**, porcentaje unificado y frase **Resultado combinado de dos modelos** o **Resultado basado en un modelo**, según la respuesta.
4. Si la API informa `coinciden` o `discrepan`, mostrar **Los modelos coinciden** o **Los modelos discrepan** dentro del panel, junto al resultado. Si no hay comparación, omitir esta línea.
5. Acceso **Ver desglose por modelo** que abre P06.
6. Acción principal **Escoger otro texto** para volver al inicio del flujo de selección.

La composición debe seguir siendo legible en el popup. Si la altura visible no alcanza, el contenido se desplaza sin ocultar el resultado ni las acciones.

## Acciones y navegación

| Acción | Resultado |
| --- | --- |
| **Ver desglose por modelo** | Abrir P06 dentro del popup con BiLSTM, mBERT y los datos disponibles de cada uno. |
| **Historial** | Abrir P07 dentro del popup. |
| **Cuenta** | Abrir P11 dentro del popup. |
| **Escoger otro texto** | Volver a P01 e iniciar una nueva selección. No repetir el análisis anterior. |

## Variantes y estados

| Situación | Presentación |
| --- | --- |
| Responden ambos modelos | Mostrar el porcentaje unificado y **Resultado combinado de dos modelos**. Si hay comparación, mostrarla junto al porcentaje. |
| Responde un modelo | Mostrar el porcentaje unificado recibido y **Resultado basado en un modelo**. En P06, el otro aparece como **No disponible**. |
| Los modelos discrepan | Mantener visible el unificado y mostrar **Los modelos discrepan** sin ocultarlo ni convertirlo en error. |
| Falta un valor unificado válido | Mostrar **Resultado unificado no disponible** y ofrecer P06 cuando haya salidas individuales. No calcular un reemplazo en el frontend. |

P04 retiene los fallos de solicitud y tiempos de espera sin respuesta concluyente. P05 solo se abre con una respuesta de análisis confirmada; no muestra un éxito ficticio tras un timeout o fallo de guardado.

## Aplicación del sistema de diseño

- Usar la cabecera, paleta, tipografía, espaciado y foco de `SISTEMA_DISENO.md`.
- El porcentaje es el único elemento numérico grande. Su color marca el eje **salida para falsa**, no un nivel de certeza o gravedad.
- Usar una fila de navegación sencilla para P06, sin convertir cada dato en una tarjeta decorativa.
- Escribir las etiquetas en lenguaje directo; no usar **Noticia falsa**, **Verídica** ni **Certeza** como veredictos.
- El color no comunica por sí solo coincidencia o discrepancia: acompañarlo de texto.
- No mostrar datos de blockchain ni una nota adicional bajo el desglose.

## Implementación

1. Crear la vista React de P05 con el panel del unificado, las filas de navegación y la acción para escoger otro texto.
2. Adaptar la respuesta real de la API al formato visual sin recalcular el unificado ni añadir clases propias.
3. Resolver las variantes de uno o dos modelos, coincidencia, discrepancia y ausencia de unificado.
4. Conectar P06, P07, P11 y el regreso a P01 dentro del popup.
5. Revisar contraste, cifras, texto largo y desplazamiento en el tamaño real del popup.

Los puntos 1 a 4 están implementados. La comprobación con una respuesta real de la API y la revisión visual en Chrome quedan pendientes. El acceso a P06 navega a su vista provisional hasta implementar esa pantalla.

## Criterios de aceptación de P05

- El porcentaje principal coincide con `resultado_unificado.probabilidad_falsa` recibido, transformado solo para mostrarlo como porcentaje.
- La vista informa si participó uno o dos modelos, según `modelos_utilizados`.
- Una discrepancia real se ve junto al resultado unificado; si no hay comparación, no se inventa una.
- P06 muestra el detalle por modelo; P05 no necesita duplicar todos sus datos.
- No aparece el estado del registro de blockchain ni un acceso a su verificación.
- No aparecen porcentajes de ejemplo, niveles inventados ni lenguaje de certeza en la pantalla real.
- Todo permanece dentro del popup y sigue `SISTEMA_DISENO.md`.

## Dependencias y siguiente pantalla

El backend debe confirmar los campos actuales de resultado unificado, modelos participantes y comparación. Esas confirmaciones están en `DEPENDENCIAS_BACKEND.md`. P06 detallará los modelos y se planificará en su propio archivo cuando el usuario indique continuar.
