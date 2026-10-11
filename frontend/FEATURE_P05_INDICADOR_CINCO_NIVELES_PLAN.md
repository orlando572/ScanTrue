# Feature P05: indicador circular y cinco niveles

## Estado y alcance

Feature implementado en P05 del popup. Reutiliza el resultado unificado que ya recibe el frontend y conserva los accesos a P06, Historial y la acción **Escoger otro texto**. No requiere modificar el backend.

Este plan actualiza las decisiones visuales y de clasificación de `PANTALLA_P05_RESULTADO_PLAN.md` y `SISTEMA_DISENO.md` solo para P05. Ambas referencias ya están alineadas con los cinco niveles aquí definidos.

## Objetivo

Mostrar el porcentaje de `resultado_unificado.probabilidad_falsa` en un anillo circular, acompañado solo por la etiqueta del nivel y un icono debajo de ella. La referencia aportada orienta la composición: cifra dentro del anillo y etiqueta a su derecha. La pantalla usará el fondo claro, la tipografía y los controles existentes de ScanTrue.

Los niveles son una **interpretación visual del porcentaje del modelo**, no una comprobación independiente de los hechos. Las etiquetas propuestas expresan probabilidad y no presentan «verdadero» o «falso» como hechos confirmados.

## Regla de los cinco niveles

Se toma el valor válido entre 0 y 1, se multiplica por 100 y se redondea al entero que aparece en pantalla. El **mismo entero visible** determina el nivel y el color; así nunca habrá un 40 % de un color reservado a 41 %. Los rangos son inclusivos y no dejan huecos.

| Porcentaje visible | Etiqueta | Color del anillo e icono | Carita bajo la etiqueta |
| --- | --- | --- | --- |
| 0–20 % | Muy probablemente verdadero | Verde profundo `#246B61` | Muy sonriente. |
| 21–40 % | Probablemente verdadero | Verde `#39784D` | Sonriente. |
| 41–60 % | Resultado incierto | Ámbar `#8B5A12` | Expresión neutra. |
| 61–80 % | Probablemente falso | Anaranjado `#AE5819` | Triste. |
| 81–100 % | Muy probablemente falso | Rojo `#A3342B` | Llorando. |

Los cinco colores están definidos como tonos propios de P05. Las dos tonalidades verdes y las dos cálidas se distinguen también por la etiqueta y el icono, sin depender solo del color.

## Composición propuesta

```text
Resultado del análisis

┌──────────────────────────────────────┐
│   ◯ 78 %    Probablemente falso      │
│             ☹                        │
└──────────────────────────────────────┘

Ver desglose por modelo               ›

Escoger otro texto
```

- Mantener un único panel destacado, sin fondo oscuro ni borde naranja decorativo de la imagen de referencia.
- Anillo a la izquierda y etiqueta a la derecha en el ancho habitual del popup. La cifra permanece dentro del anillo y es legible incluso en 0 % y 100 %.
- El arco coloreado representa el porcentaje; el resto usa un trazo neutro. Su color cambia con el nivel, sin gradiente ni animación necesaria para entenderlo.
- La carita cambia gradualmente de muy sonriente a llorando y se coloca debajo de la etiqueta, nunca a su lado. El panel solo contiene anillo, porcentaje, etiqueta y carita.
- No mostrar en P05 frases sobre cuántos modelos participaron ni si coincidieron o discreparon. El desglose por modelo sigue accesible desde su botón fuera del panel.
- Si el ancho disponible resulta insuficiente, apilar anillo y etiqueta dentro del mismo panel sin truncar el texto ni crear desplazamiento horizontal.

## Tecnología propuesta

Usar SVG nativo dentro de React para dos círculos: pista y arco de progreso. No añadir una librería de gráficos para un único indicador. Tailwind y los tokens actuales controlarán tamaño, separación, color y foco. Respetar la preferencia de movimiento reducido si se decide animar el arco; la primera versión puede ser estática.

## Datos y estados

| Estado | Comportamiento |
| --- | --- |
| Valor válido del resultado unificado | Mostrar anillo, entero redondeado, nivel y color correspondientes. |
| 0 % o 100 % | Mostrar el extremo exacto sin esconder la cifra o la etiqueta. |
| Un solo modelo disponible | Mostrar únicamente el nivel del unificado recibido; no añadir leyenda sobre modelos. |
| Dos modelos disponibles | Mostrar únicamente el nivel del unificado recibido; no añadir leyenda sobre modelos. |
| Modelos discrepantes | El nivel sigue derivándose solo del unificado recibido; no mostrar la comparación en P05. |
| Valor unificado ausente o inválido | Mostrar **Resultado unificado no disponible** sin anillo activo, nivel ni porcentaje inventado. Mantener P06 si existen salidas individuales. |

P05 no recalcula el resultado unificado ni modifica la respuesta de la API. Los rangos son solo reglas de presentación del frontend.

## Implementación y verificación

1. Actualizar las reglas de P05 en el sistema de diseño y el plan original para que el vocabulario y los colores no se contradigan.
2. Añadir al presentador de P05 una función pura que transforme la probabilidad válida en porcentaje visible y nivel, con límites inclusivos.
3. Crear el anillo SVG y la disposición del panel en React y Tailwind, reutilizando los estilos del popup.
4. Incorporar las cinco etiquetas, colores e iconos con texto accesible y contraste suficiente.
5. Quitar del panel de P05 las frases sobre modelos participantes y coincidencia; conservar los datos para P06 y el estado sin valor unificado.
6. Verificar los límites 0, 20, 21, 40, 41, 60, 61, 80, 81 y 100 %, además de decimales que se redondean en un límite.
7. Revisar P05 en Chrome al tamaño real del popup, con teclado, zoom y textos largos, y ejecutar pruebas y compilación del frontend.

Los pasos 1 a 6 están implementados. Las pruebas y la compilación del paso 7 están verificadas; la revisión visual interactiva en Chrome sigue pendiente.

## Criterios de aceptación

- Hay exactamente cinco niveles, sin huecos ni solapamientos, calculados a partir del porcentaje que el usuario ve.
- Un resultado de 78 % muestra **Probablemente falso** con anillo anaranjado y una carita triste debajo de la etiqueta.
- La cifra, el texto y el icono transmiten el resultado sin depender únicamente del color.
- El panel no muestra «Según el análisis» ni frases sobre cantidad o coincidencia de modelos.
- No se añaden dependencias de gráficos, valores de ejemplo en producción ni cambios en el backend.
- P06, Historial y **Escoger otro texto** conservan su comportamiento.
