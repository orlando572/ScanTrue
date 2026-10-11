# Feature P06: tarjetas de BiLSTM y mBERT

## Estado y alcance

Feature implementado en la presentación de BiLSTM y mBERT en P06 del popup. No modifica el backend, la respuesta de la API, P05 ni el historial. La navegación **Volver** conserva su comportamiento. P06 no muestra mensajes de comparación entre modelos.

Este feature toma de las imágenes de referencia la composición compacta: icono, nombre, insignia de clase, porcentaje y barra. El estilo final seguirá el fondo claro, la tipografía y los bordes discretos de `SISTEMA_DISENO.md`.

## Objetivo

Permitir comparar de un vistazo las salidas individuales de BiLSTM y mBERT. Cada tarjeta debe identificar claramente a su modelo y mostrar solo datos reales de ese modelo, sin convertir el porcentaje en una afirmación de veracidad comprobada.

## Datos y significado

| Dato recibido | Uso en la tarjeta |
| --- | --- |
| `resultados.bilstm` y `resultados.mbert` | Una tarjeta por modelo, siempre en ese orden. |
| `estado` | Decidir si la salida está disponible. Solo `ok` permite presentar porcentaje y clase. |
| `clase` | Insignia **FALSA** o **REAL** si el valor recibido es válido. No deducirla del porcentaje. |
| `probabilidad_falsa` | Porcentaje grande, longitud de la barra y etiqueta de uno de los cinco niveles de P05, tras validar que sea un número entre 0 y 1. |

El porcentaje y la barra expresan **salida para falsa**. El comentario junto a cada porcentaje usa las mismas cinco etiquetas de P05, según el valor redondeado de ese modelo. Las clases de la insignia son predicciones recibidas; no constituyen una verificación de hechos.

## Composición propuesta

Diseñar dos tarjetas compactas **apiladas**. Dentro de los 400 px del popup, esto deja espacio suficiente para nombre, insignia y cifras sin reducirlos demasiado. Las imágenes sirven como referencia de la distribución interior de cada tarjeta, no del ancho ni de sus colores exactos.

```text
Desglose por modelo

┌────────────────────────────────────┐
│ [icono] BiLSTM             [FALSA] │
│ 91 %          Muy probablemente     │
│               falso                │
│ ██████████████████░░              │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ [icono] mBERT              [FALSA] │
│ 98 %          Muy probablemente     │
│               falso                │
│ ████████████████████              │
└────────────────────────────────────┘

Los modelos analizan las palabras y su contexto, pero no
comprueban los hechos con fuentes externas.
```

- Encabezado: icono SVG pequeño distinto para cada modelo, nombre exacto **BiLSTM** o **mBERT** e insignia alineada a la derecha.
- Cuerpo: porcentaje destacado a la izquierda y etiqueta del nivel correspondiente a la derecha. La cifra será menor que el porcentaje unificado de P05.
- Pie: barra horizontal sobre una pista neutra. Su longitud corresponderá al mismo entero redondeado que aparece en la cifra. La pista completa permanece visible en 0 %.
- Color: rojo para una clase `falsa`, verde para `real` y neutro si no hay clase válida. Insignia, porcentaje y barra comparten el tono; el texto mantiene el significado aunque no se distinga el color.
- Tarjetas con borde sutil y separación clara. Evitar sombras, animaciones continuas y elementos decorativos añadidos.
- Bajo las tarjetas, mostrar siempre la nota fija sobre el alcance y la limitación de los modelos. No mostrar mensajes de coincidencia o discrepancia.

## Estados

| Situación | Presentación |
| --- | --- |
| Modelo con `estado: ok`, probabilidad y clase válidas | Mostrar insignia, porcentaje y barra correspondientes a ese modelo. |
| Probabilidad válida, clase ausente o inesperada | Mostrar porcentaje y barra en tono neutro; omitir la insignia. No inferir `real` o `falsa`. |
| Modelo ausente, fallido o con probabilidad inválida | Mantener nombre e icono; mostrar **No disponible**. Omitir porcentaje, insignia y barra activa. |
| Ambos modelos válidos | Mostrar las dos tarjetas, cada una con su propia etiqueta de nivel. |
| Solo un modelo válido | Mostrar su tarjeta completa y la otra como **No disponible**. |
| Ningún modelo válido | Mantener ambas tarjetas en estado **No disponible** y el mensaje general existente. |
| 0 % o 100 % | Mostrar el valor exacto; la barra queda vacía o llena sin reemplazar el porcentaje por otro dato. |

## Implementación y verificación

1. Actualizar `PANTALLA_P06_DESGLOSE_PLAN.md` y la regla de desglose de `SISTEMA_DISENO.md` para incorporar las tarjetas y el significado de la barra.
2. Ampliar el presentador de P06 para validar `clase` y exponer el porcentaje numérico necesario para la barra, sin alterar el cálculo de P05 ni P08.
3. Crear una tarjeta reutilizable para BiLSTM y mBERT con sus iconos SVG propios, nombre, insignia, cifra, texto y barra.
4. Aplicar los estilos del sistema de diseño y comprobar la disposición en el ancho real del popup y con zoom.
5. Conservar los estados de indisponibilidad, retirar la comparación, colocar la nota fija y mantener la navegación desde P05 y P08.
6. Probar clases `falsa` y `real`, clase ausente, modelos ausentes, 0 %, 100 %, valores inválidos y los cinco niveles; compilar el frontend.
7. Revisar las dos tarjetas visualmente en Chrome con respuestas reales de ambos modelos cuando estén disponibles.

El código y los estilos de los pasos 1 a 6 están implementados; las pruebas y la compilación pasaron. La revisión visual interactiva en Chrome, incluido el zoom y respuestas reales de ambos modelos, sigue pendiente.

## Criterios de aceptación

- BiLSTM aparece antes que mBERT; cada tarjeta conserva su identidad y sus propios datos.
- El porcentaje mostrado y la barra usan el mismo valor redondeado de `probabilidad_falsa` del modelo correspondiente.
- La insignia procede exclusivamente de `clase` y nunca se inventa a partir del porcentaje.
- Cada tarjeta muestra la etiqueta del nivel que corresponde a su porcentaje. La nota fija explica que los modelos analizan palabras y contexto, sin verificar hechos con fuentes externas.
- Un modelo no disponible no presenta 0 % ni una barra que pueda confundirse con un resultado real.
- P06 no muestra avisos de coincidencia ni de discrepancia entre modelos.
- Todo permanece dentro del popup y no requiere dependencias nuevas ni cambios en el backend.
