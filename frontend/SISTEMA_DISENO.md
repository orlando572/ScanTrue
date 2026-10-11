# Sistema de diseño de ScanTrue

## Propósito

Definir el lenguaje visual y de interacción que compartirán las vistas P01, P02, P04 a P09 y P11 a P13 del popup. Este documento orienta el diseño de cada pantalla; no es un prototipo final ni implementa componentes. Antes de construir cada pantalla se preparará, con el usuario, su archivo independiente de planificación e implementación.

Las cuatro imágenes entregadas sirven como referencia de jerarquía: cabecera compacta, acción principal evidente, resultado destacado, desglose plegable e historial fácil de recorrer. Sus textos y colores no son un contrato funcional. El alcance y los estados se toman de `FEATURE_01_ALCANCE_Y_RECORRIDOS.md` y los datos reales se mostrarán según la API.

## Dirección visual

**Concepto: ficha de lectura.** ScanTrue se sentirá como una herramienta que ayuda a examinar un fragmento, no como una alarma que dicta un veredicto. La selección textual es la pieza central; los resultados se presentan como mediciones atribuidas a modelos. Una línea lateral fina identifica la selección y reaparece en el detalle histórico para conectar ambos momentos.

- Interfaz minimalista, fondo claro y una única zona de énfasis por vista.
- Contenido y títulos alineados a la izquierda. Centrar solo un estado vacío o una acción aislada, cuando ayude a orientar la mirada.
- Superficies planas y bordes discretos. Reservar el color intenso para la acción primaria, el foco y los datos que lo necesiten.
- El porcentaje puede ser grande en el resultado, pero siempre junto a su nombre y explicación. No usar un número aislado como supuesto veredicto.
- Evitar gradientes decorativos, sombras en todas las tarjetas, iconos redundantes y etiquetas en mayúsculas sostenidas.

## Paleta semántica

Los valores son la propuesta inicial del sistema; se ajustarán si la revisión visual de las pantallas muestra problemas de contraste.

| Token | Valor | Uso |
| --- | --- | --- |
| `canvas` | `#F3F7F7` | Fondo del popup. |
| `surface` | `#FFFFFF` | Área principal, tarjetas y formularios. |
| `ink` | `#17324D` | Títulos, texto principal e iconos importantes. |
| `muted` | `#506575` | Descripciones, fecha y datos secundarios. |
| `line` | `#D6E1E4` | Separadores y contornos de campos. |
| `accent` | `#087D77` | Acción principal, selección y foco activo. |
| `accent-soft` | `#E2F2EF` | Fondo de una selección o estado activo. |
| `false` | `#A3342B` | Salida de clase falsa y error; siempre acompañada de texto. |
| `false-soft` | `#F9EAE7` | Fondo suave para esa salida. |
| `real` | `#246B61` | Salida de clase real; no significa verificación factual. |
| `real-soft` | `#E8F2EF` | Fondo suave para esa salida. |
| `warning` | `#8B5A12` | Pendiente o atención sin fallo confirmado. |
| `warning-soft` | `#FFF3DB` | Fondo de aviso. |
| `focus` | `#1265AC` | Anillo de foco de teclado claramente visible. |

Los estados nunca dependerán solo del color: cada uno tendrá nombre, icono cuando aporte información y texto explicativo.

## Tipografía

- **Familia propuesta:** IBM Plex Sans, incluida localmente en el paquete de la extensión si se adopta en la implementación. Respaldo: fuentes sans serif del sistema. No depender de una fuente cargada desde internet.
- **Números:** usar cifras tabulares para porcentajes, fechas y métricas comparables. Evitar una tipografía distinta solo para cifras pequeñas.
- **Escala:** título de vista 20/26 seminegrita; título de sección 16/22 seminegrita; texto principal 14/20 regular; texto auxiliar 12/17 regular; dato destacado 40/44 seminegrita. Los tamaños se podrán ajustar en la revisión visual del popup.
- **Caja:** frases normales, sin mayúsculas sostenidas salvo siglas y nombres de modelos. Mantener el texto de lectura en líneas cortas.

## Dimensiones, espaciado y forma

- Diseñar para un popup angosto; referencia inicial de trabajo: **400 px de ancho**. El alto visible dependerá del navegador. Las vistas largas se desplazan dentro del popup.
- Margen horizontal principal: 20 px. Separación entre secciones: 24 px. Separación entre elementos relacionados: 8 o 12 px.
- Escala de espaciado: 4, 8, 12, 16, 20, 24 y 32 px. Elegir de esta escala antes de crear excepciones.
- Radio: 10 px en campos y botones; 14 px en paneles de contenido. Evitar que cada elemento parezca una tarjeta independiente.
- Bordes de 1 px para estructurar; sombra solo donde ayude a distinguir un elemento flotante, como una confirmación.
- Área interactiva cómoda para ratón y teclado; los iconos de cabecera tendrán nombre accesible y foco visible.

## Estructura común del popup

```text
┌──────────────────────────────────────────────┐
│ ScanTrue          historial  cuenta  cerrar  │
│ Título de vista                 volver, si aplica
├──────────────────────────────────────────────┤
│                                              │
│ Contenido propio de la vista                 │
│ Una acción principal claramente identificada│
│ Estados y ayuda cerca de la acción afectada  │
│                                              │
└──────────────────────────────────────────────┘
```

La cabecera conserva la identidad y la navegación esencial. En vistas secundarias, **Volver** regresa a la vista anterior del popup; **Cerrar** cierra el popup y no equivale a cerrar sesión. Evitar más de una acción primaria a la vez. Si el contenido supera el alto disponible, desplazar el cuerpo y mantener visibles los controles solo cuando no oculten información.

## Componentes y patrones compartidos

| Elemento | Regla de diseño |
| --- | --- |
| Cabecera | Logotipo compacto de lupa con marca de verificación y nombre ScanTrue; ambos forman un botón que vuelve a P01. Título de vista y acciones con iconos reconocibles y etiquetas accesibles. Historial y cuenta son accesos dentro del popup. |
| Botón principal | Ancho completo cuando guía el paso central; verbo concreto: **Escoger texto**, **Analizar**, **Iniciar sesión**. Estado deshabilitado con explicación cuando falte un requisito. |
| Botón secundario | Contorno o texto para **Seleccionar de nuevo**, **Cancelar**, **Volver** y **Actualizar**. No competir visualmente con el principal. |
| Selección de texto | Fragmento en un panel con línea lateral `accent`, vista previa legible y desplazamiento si es largo. Mostrar que pertenece a la página elegida. |
| Resultado | P05 muestra el porcentaje unificado en un anillo, la etiqueta de uno de cinco niveles y su icono debajo. P06 conserva el detalle de BiLSTM y mBERT. |
| Desglose | Desde el resultado, una fila abre P06 dentro del popup. BiLSTM y mBERT aparecen en tarjetas compactas con nombre, clase recibida, porcentaje, etiqueta de uno de cinco niveles y barra. Debajo se explica que los modelos no comprueban hechos con fuentes externas. Un modelo sin predicción muestra **No disponible**, no 0 %. |
| Historial | Lista de filas compactas con fecha, vista previa y salida guardada. La fila entera abre el detalle; la eliminación se solicita dentro del detalle o mediante acción claramente asociada al registro. |
| Pruebas del modelo | Nombre del conjunto, porcentaje de aciertos y número de textos evaluados; origen breve cuando exista y limitaciones en un apartado desplegable. Estas cifras no son la puntuación de la noticia abierta. |
| Formularios | Una columna, etiquetas visibles, errores bajo el campo y mensajes generales al inicio del formulario. Contraseñas nunca se muestran en registros de consola. |
| Confirmación | Título directo, consecuencia concreta y dos acciones. |
| Avisos | Mensaje breve que explique lo ocurrido y el siguiente paso. Errores de API transformados a lenguaje de interfaz, sin JSON crudo. |

## Reglas de contenido

En las pantallas de inicio y selección, usar instrucciones breves en lenguaje cotidiano. Reservar términos como **BiLSTM**, **mBERT** y **resultado unificado** para el resultado, el desglose y las métricas, donde ayudan a interpretar datos concretos.

| Evitar | Preferir |
| --- | --- |
| “Certeza global de desinformación” | “Salida unificada para falsa” |
| “Noticia falsa” como hecho confirmado | “El modelo favorece la clase falsa” cuando esa clase llegue de la API |
| “Verídica” como veredicto | “El modelo favorece la clase real” cuando esa clase llegue de la API |
| “98 % de certeza” | “98 % de salida para falsa” |

El porcentaje mostrado será el valor de la API multiplicado por 100 y redondeado. El resultado unificado y sus pesos vendrán del backend. P05 y las tarjetas individuales de P06 asignan los cinco niveles visuales definidos en `FEATURE_P05_INDICADOR_CINCO_NIVELES_PLAN.md`. P06 no muestra comparaciones entre modelos. Los niveles expresan la salida del modelo, no una verificación independiente de los hechos.

## Comportamiento de los estados

- **Sin selección:** mostrar una explicación breve y la acción **Escoger texto**.
- **Selección pendiente:** reflejar el fragmento capturado; ofrecer **Analizar** o **Seleccionar de nuevo**. Mostrar junto a la acción un aviso breve sobre el envío y guardado del texto. Al pulsar **Analizar**, iniciar el análisis y mostrar P04 directamente.
- **Carga:** identificar la operación y evitar el doble envío. No usar animaciones continuas llamativas.
- **Resultado parcial:** mostrar el valor de cada modelo disponible y **No disponible** para el que falló, sin inventar porcentajes.
- **Vacío:** explicar por qué no hay elementos y ofrecer la acción que permite empezar; en historial, volver a analizar.
- **Error recuperable:** mostrar causa comprensible y una acción concreta. En timeout tras enviar un análisis, orientar a revisar el historial antes de repetirlo.
- **Sesión pendiente de confirmación:** mantener visible el siguiente paso y no presentar la cuenta como activa ni perder la sesión invitada.

## Movimiento y accesibilidad

- Animar solo cambios provocados por el usuario, como abrir el desglose o cambiar de vista, con transiciones breves. Respetar la preferencia de movimiento reducido.
- Mantener navegación por teclado, orden de foco lógico, foco visible y nombres accesibles en botones de icono.
- No usar rojo y verde como única diferencia entre clases. Incluir etiqueta textual y valor.
- En contenido largo, evitar que el desplazamiento o una barra fija oculten el botón para volver o la confirmación de una acción.

## Cómo se aplicará pantalla por pantalla

Este sistema se aplicará en el orden P01, P02, P04 a P09 y P11 a P13. Antes de iniciar cada pantalla, se pedirá al usuario crear su archivo separado de planificación e implementación y se revisará el material visual que comparta. La pantalla se diseñará con estos tokens y patrones, se comprobará en el tamaño real del popup y solo entonces se pasará a la siguiente. Las excepciones al sistema se documentarán en el archivo de esa pantalla.
