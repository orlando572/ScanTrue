# Sistema de diseño de ScanTrue

## Propósito

Este documento define el lenguaje visual y de interacción de las vistas P01, P02, P04 a P09 y P11 a P13 del popup. El rediseño de noviembre de 2026 sustituye la dirección anterior («ficha de lectura», fondo claro). **Solo cambia el aspecto:** pantallas, textos funcionales, estados y comportamiento se mantienen.

## Dirección visual

**Concepto: consola de análisis ScanTrue, terminal de vigilancia de información, 1995.** Se parece a un sistema informático especializado que imaginaba el futuro en los años 90, con la usabilidad de hoy. Referencias de composición: interfaces de ciencia ficción retro de los 80 y 90 (retículas vectoriales, centros de control, pantallas CRT), paneles técnicos del anime de esa época (módulos con código, alertas jerarquizadas, varios colores con significado) y el *cassette futurism* (teclas físicas, LEDs, reglas graduadas).

- Fondo CRT casi negro y azulado, con retícula de 20 px, viñeta y líneas de escaneo.
- Paneles modulares con dos esquinas cortadas y dos en escuadra. Los títulos van solos: sin códigos de panel ni de módulo encima.
- Geometría vectorial luminosa: radar, dial segmentado, reglas, barras por segmentos.
- Varios colores con función fija (tabla de paleta). El color nunca es la única señal.
- **Evitar:** dashboard SaaS moderno (tarjetas redondeadas, sombras suaves), estética *gamer* actual (RGB, biseles agresivos) y terminal verde monocromática.

## Paleta

Los tokens viven en `@theme` de `src/popup/styles.css`. Los nombres antiguos se conservan, así que las utilidades de Tailwind (`text-muted`, `border-line`…) usan los valores nuevos.

| Token | Valor | Uso |
| --- | --- | --- |
| `canvas` | `#05080F` | Fondo del popup, con retícula. |
| `surface` | `#0A1220` | Paneles. |
| `surface-2` | `#0F1B2E` | Campos, filas en hover. |
| `line` | `#1E3A5C` | Bordes, retícula, segmentos apagados. |
| `ink` | `#E6F4FF` | Texto principal. |
| `muted` | `#8FA8C4` | Texto secundario (contraste AA sobre `surface`). |
| `accent` | `#38E1FF` | Cian: acción principal, marcos, iconos, búfer de entrada. |
| `amber` | `#FFB21E` | Contadores y rótulos de estado, avisos, servicio degradado. |
| `magenta` | `#FF3D7F` | Énfasis secundario: índices, desglose, órdenes de borrado. |
| `false` | `#FF4A3D` | Clase falsa y errores; siempre con texto. |
| `real` | `#3DFF9A` | Clase real y servicio disponible; no significa verificación factual. |
| `focus` | `#FFE45C` | Anillo de foco de teclado. |

Escala de los cinco niveles del resultado (`result-panel--*`): `very-low` `#3DFF9A`, `low` `#2EE6C8`, `middle` `#FFB21E`, `high` `#FF7A1A`, `very-high` `#FF4A3D`. Siempre va acompañada de la etiqueta del nivel, el glifo y la escala «Nivel n/5».

## Tipografía

Las tres familias van empaquetadas con `@fontsource` (sin peticiones a internet):

- **Orbitron** (`--font-display`, 500 y 700): marca y títulos de vista (`.screen-title`), en mayúsculas mediante CSS.
- **Share Tech Mono** (`--font-mono`): rótulos, etiquetas, botones, cifras, fechas y lecturas.
- **IBM Plex Sans** (`--font-sans`): textos de lectura, mensajes y contenido de noticias, en frase normal.

Cifras: Share Tech Mono con `tabular-nums`. Las mayúsculas sostenidas se limitan a rótulos, botones y títulos cortos. Los párrafos no.

## Dimensiones y forma

- Ancho de trabajo: **panel lateral** (de 320 px en adelante; el contenido se adapta) y **400 px** en el popup. Margen horizontal: 20 px. Escala de espaciado: 4, 8, 12, 16, 20, 24 y 32 px.
- Sin radios: los paneles tienen esquinas cortadas de 14 px (`.hud-panel`) y las teclas, chaflanes de 10 px.
- Bordes de 1 px. El brillo (`box-shadow`, `text-shadow`, `drop-shadow`) se reserva para datos, LEDs y estados activos.

## Componentes

| Elemento | Regla de diseño |
| --- | --- |
| Cabecera (`.console-header`) | Fija arriba. Logo «almendra-radar» (`scantrue-mark.svg`): un ojo curvo cian cuya pupila es un radar con barrido y un contacto ámbar, dentro del marco de esquinas cortadas; examina sin prometer un veredicto, así que la marca nunca usa ✓ ni símbolos de verificación. «SCAN//TRUE» en Orbitron y «Análisis de noticias». Accesos a historial, pruebas y cuenta como teclas iluminadas. Debajo, la tira de LEDs y la regla (`LedStrip`). |
| Encabezado de vista (`ScreenHeader`) | Tecla volver y título en Orbitron, sin código encima. Mantiene `aria-label`, `title` e `id` de cada pantalla. |
| Panel (`.hud-panel`) | Esquinas cortadas, escuadras de 2 px y color configurable con `--panel-color` (`--amber`, `--magenta`, `--false`). |
| Rótulo (`.hud-code`) | Rótulo mono en mayúsculas y en español, solo como contador o rótulo de sección con dato: «Registro de operaciones · 005 entradas», «Búfer de entrada · 206 car.», «Sin conexión». **Siempre con `aria-hidden`**: es decoración y no sustituye ningún texto. No se usan códigos de panel («Panel 05 · …»), de módulo («Módulo 01 · …») ni rótulos que repitan el título. |
| Botón principal | Tecla cian con chaflán y texto oscuro mono, sin adornos internos. Uno por vista. |
| Botón secundario | Tecla de hardware azul acero con borde, también en los chaflanes. Variante de borrado con borde rojo; la confirmación es una tecla roja. |
| Campos | Fondo hundido `surface-2`, base de 2 px, cursor cian, texto mono y etiqueta mono cian. El error pinta el borde de rojo y aparece debajo con ▲. |
| Selección (P02) | Mientras el modo selección está activo, una etiqueta pequeña «● Seleccionando» (LED ámbar) bajo el título; la fila «Fragmentos · N marcados» tiene el enlace **Vaciar** para empezar de cero; se termina desde la barra de la página o al pulsar **Analizar**. Orden: medidor de longitud, **Analizar** justo debajo (con su mensaje de error, si lo hay), fragmentos, «Editar texto completo» y, al final, «Seleccionar más texto». Medidor «Longitud · N palabras» con barra de 24 segmentos de 0 a ~350 palabras y muesca en el mínimo (100). Colores por nivel: **rojo** < 100 («Faltan N palabras»), **amarillo** 100–279 («Listo para analizar»), **verde** 280–349, el 80 % del máximo («Buena longitud»), y **dorado** con brillo metálico ≥ 350 («Longitud completa: lo que siga no se analiza»). «Editar texto completo» empieza cerrado y su cuadro crece con el contenido (mínimo ~3 líneas, máximo 220 px). Lista de fragmentos con índice magenta `#01`, barra lateral cian y botón **Quitar**. El texto completo se edita en un desplegable. |
| Texto analizado (P08) | Búfer con barra lateral cian y brillo, rótulo «Texto archivado». |
| Barra en la página | Durante el modo selección: una sola línea fija abajo (Shadow DOM, 44 px de alto): LED ámbar, «Seleccionando» y, hasta el primer fragmento, la pista «Marca texto en la página para añadirlo»; después, «N fragmentos · N palabras» (palabras en ámbar hasta el mínimo, verde al alcanzarlo). Botones **Vaciar** (solo con fragmentos) y **Terminar**. Los fragmentos se resaltan en cian con `::highlight(scantrue-fragment)`; un clic sobre uno ofrece **Quitar fragmento**. El detalle (lista y medidor) queda en el panel. |
| Resultado (P05, P08) | Dial de 40 segmentos en un arco de 270°, regla 0/50/100 y aguja. Porcentaje mono grande centrado en el aro: solo las cifras se centran y el «%» cuelga a la derecha; el tamaño depende del ancho del dial (`cqi`, más pequeño con 100). El rótulo «Salida para falsa» va bajo la regla 0/100, en el hueco del arco, para que no se lea como «probabilidad de ser verdadero». El dial no se estira con la altura del veredicto. El veredicto es una rejilla de tres filas: glifo arriba, etiqueta en la fila central y escala abajo; la etiqueta se ajusta a su columna (`cqi`) para que «PROBABLEMENTE» quepa sin cortarse. **Glifos de nivel** dentro del hexágono, sin caras: doble hexágono con ✓ (1), ✓ (2), ? (3), ! (4) y doble hexágono con ✕ (5). **Al aparecer:** la aguja barre desde 0, los segmentos se encienden en orden, el número cuenta hasta el valor (1 s), el glifo se traza y su anillo exterior late (más rápido en el nivel 5; la ? parpadea despacio). Debajo, en cascada y con un parpadeo de encendido: **espectro** Real–Incierto–Falso de cinco zonas con BETO (▼ violeta, encima), BiLSTM (▲ cian, debajo) y el combinado (rombo del color del nivel), que viajan desde 0 hasta su posición; al pie del mismo panel, el **acuerdo entre modelos** (`comparacion`), solo con su título: dos luces de los modelos unidas por un cable con pulsos si coinciden, cortado con ✕ ámbar si no coinciden o con una sola luz si solo respondió uno. El borde del panel toma ese color (cian, ámbar o gris) y es más opaco que el de un panel normal; las etiquetas de BETO y BiLSTM quedan separadas de su flecha y del borde. **Lectura**, panel propio: palabras del texto analizado, página de origen (dominio en ámbar con LED, enlace a la URL) y, en P05, un fragmento del comienzo (≤ 180 caracteres, sin partir palabras) con **Ver texto completo** para desplegarlo; en P08 el texto ya está arriba, así que solo muestra palabras y página. El estado del registro en blockchain no se muestra en el resultado: la respuesta de `POST /analisis` siempre dice «pendiente» y el registro se completa segundos después. Al final, el acceso al desglose y la `nota` del backend. Presentación en `presentInsights` (`result-presentation.js`). |
| Desglose (P06) | Un módulo por modelo, con icono vectorial, LED FALSA/REAL, porcentaje y barra de 20 segmentos. «No disponible» si falta la predicción. |
| Historial (P07) | Registro de operaciones: índice `#001`, fecha mono, vista previa, página de origen en ámbar con LED (también en el encabezado de P08), porcentaje con color de nivel y barra cian al pasar el ratón. |
| Pruebas (P09) | Cada modelo con el color de su luz en la tira de estado (BiLSTM cian, mBERT violeta): icono vectorial (`ModelIcon`, compartido con P06) en un cuadro de su color, nombre en Orbitron de su color, contador «N pruebas» en ámbar y panel con borde y escuadras de su color. Cada conjunto lleva una etiqueta de color por tipo (Validación verde, Prueba interna magenta, Fuentes reservadas o Prueba externa ámbar) y la cantidad de textos a la derecha. «Aciertos» en grande con barra de 25 segmentos del color del modelo; **F1** como segunda barra fina en magenta. De entrada solo se ven las pruebas principales —**Prueba congelada** (evaluación final) y **Fuentes no vistas**—, cada una con una línea que explica qué mide; el resto (fuentes no vistas por separado y FalleDesinfo) se despliega con **Ver N pruebas más**, al pie del panel de cada modelo y en su color. «Sobre estas pruebas» es un desplegable con cuatro frases en lenguaje cotidiano escritas en el frontend (qué son los aciertos y F1, qué es la prueba congelada y que los modelos no comprueban hechos); las limitaciones técnicas del backend no se muestran. |
| Cuenta y acceso (P11–P13) | Avatar vectorial (128 px) en retícula giratoria y mensaje de estado en Orbitron mayúscula (`.account-status`), centrados en vertical entre el encabezado y los botones; el correo, debajo, en mono. Formularios dentro de una «Terminal de autenticación». El «Mensaje del sistema» de sesión iniciada (con o sin historial incorporado) se cierra solo a los 6 s, con una barra ámbar de cuenta atrás en su borde inferior y un desvanecido final; el de cuenta pendiente de confirmación es persistente porque pide un paso al usuario. |
| Confirmación de borrado | Panel rojo con banda de advertencia diagonal, título directo y dos teclas. |
| Estado del servicio | Tira bajo la cabecera, visible en todas las vistas, con **una luz por servicio real de `/salud`**, cada una con su color cuando funciona: BiLSTM cian, mBERT violeta, Cuentas e historial verde, Registro blockchain azul hielo. **Rojo** = caído (parpadea), **ámbar** = falla en parte o sin datos, apagada con parpadeo = comprobando. Si la tira tiene sitio, cada luz lleva su nombre corto; si no, solo la luz, con el nombre en `title` y para lectores de pantalla. Las luces que funcionan tienen «actividad de datos»: parpadeos breves con un ritmo aleatorio propio (2,5–6 s), nunca todas a la vez; las rojas parpadean a ritmo fijo de alarma. Entre las luces y el estado, un **bus de datos**: una regla fina por la que viajan pulsos de los colores de los servicios activos (más rápido al comprobar, detenido y en rojo con la API caída). A la derecha, el resumen «En línea / Servicio limitado / Sin conexión / Conectando… / Estado desconocido» con la latencia medida de `/salud` («En línea · 24 ms»). Lógica en `service-presentation.js`. Si la API no responde, P01 muestra junto al botón un panel con el mensaje y **Reintentar**. |
| Inicio (P01) | En el panel lateral ocupa todo el alto: el radar, con dos anillos exteriores, se centra en el espacio libre y la tarjeta de acción queda abajo. |
| Escala | Toda la interfaz usa `zoom: var(--ui-zoom)` (1,12). En paneles de menos de 360 px vuelve a 1 para que nada desborde. |
| Ancho estable | `html` reserva siempre el hueco de la barra de desplazamiento (`scrollbar-gutter: stable`): el contenido no cambia de ancho cuando la barra aparece. Los títulos de vista se ajustan al ancho (`clamp`) y, si se partieran, se reparten con `text-wrap: balance`. |

## Icono de la extensión

`public/icons/icon-{16,32,48,128}.png`, declarados en `icons` y `action.default_icon` del manifiesto. 48 y 128 px salen del logo completo; 16 y 32 px, de `scantrue-mark-small.svg`: el mismo ojo con trazo más grueso y sin el anillo interior, para que se lea en la barra de Chrome.

## Decoración

- **Global:** retícula, viñeta, líneas de escaneo y un barrido CRT lento (pseudo-elementos fijos con `pointer-events: none`). Al abrir, un parpadeo breve de encendido.
- **Entrada de vistas (`.screen-boot`):** los bloques de primer nivel de cada vista se encienden en cascada (parpadeo `module-boot`, 80 ms entre bloques). Se aplica en la raíz de P06–P09 y P11–P13, y en `main` para P01 y P02. P04 y P05 tienen animaciones propias. La regla tiene especificidad nula: un bloque con animación propia conserva la suya. Además, las filas del historial se escriben una tras otra y las barras de aciertos y del desglose encienden sus segmentos en orden.
- **P01:** radar con barrido, contactos y objetivo sobre un fragmento de texto.
- **P04:** el mismo radar con barrido rápido, tres bloques de barras de nivel (cian, ámbar y magenta) sin rótulo y un flujo hexadecimal.
- Los gráficos decorativos están en `src/popup/components/HudDecor.jsx` y siempre llevan `aria-hidden`.

## Reglas de contenido

En el inicio, hablar como a alguien que no conoce los modelos: «Marca el titular y unos párrafos de la noticia. Te mostramos si se parece más a una noticia falsa o a una real.», seguido siempre de la aclaración «Es una orientación, no una verificación de los hechos.».

En las pantallas de inicio y selección, usar instrucciones breves en lenguaje cotidiano. Reservar términos como **BiLSTM**, **mBERT** y **resultado unificado** para el resultado, el desglose y las métricas, donde ayudan a interpretar datos concretos.

| Evitar | Preferir |
| --- | --- |
| “Certeza global de desinformación” | “Salida unificada para falsa” |
| “Noticia falsa” como hecho confirmado | “El modelo favorece la clase falsa” cuando esa clase llegue de la API |
| “Verídica” como veredicto | “El modelo favorece la clase real” cuando esa clase llegue de la API |
| “98 % de certeza” | “98 % de salida para falsa” |

El porcentaje mostrado será el valor de la API multiplicado por 100 y redondeado. El resultado unificado y sus pesos vendrán del backend. P05 y las tarjetas individuales de P06 asignan los cinco niveles visuales definidos en `FEATURE_P05_INDICADOR_CINCO_NIVELES_PLAN.md`. P06 no muestra comparaciones entre modelos; el acuerdo entre ellos se resume en P05 y P08. Los niveles expresan la salida del modelo, no una verificación independiente de los hechos.

## Comportamiento de los estados

- **Sin selección:** mostrar una explicación breve y la acción **Escoger texto**.
- **Selección pendiente:** reflejar el fragmento capturado; ofrecer **Analizar** o **Seleccionar de nuevo**. Mostrar junto a la acción un aviso breve sobre el envío y guardado del texto. Al pulsar **Analizar**, iniciar el análisis y mostrar P04 directamente.
- **Carga del análisis (P04):** identificar la operación y evitar el doble envío. La animación de espera (radar y barras) es decorativa y se detiene con movimiento reducido. No usa el estándar de carga de abajo.
- **Carga de datos (estándar, `HudLoader`):** nunca un texto «Cargando…» suelto. Rótulo mono corto en cian con cursor parpadeante (`code`: «Recuperando registros», «Abriendo archivo», «Consultando pruebas», «Verificando sesión»), una barra de 14 segmentos que recorre una luz y el esqueleto de lo que va a aparecer, con una línea de escaneo: filas para el historial (`shape="rows"`), paneles para detalle y pruebas (`"panels"`) y avatar para la cuenta (`"account"`). El texto completo («Cargando historial»…) va en `label`, solo para lectores de pantalla, con `role="status"`. Aparece con 150 ms de retraso para que una respuesta rápida no parpadee. En botones («Cargar más») se usa solo la barra (`LoaderSweep`).
- **Resultado parcial:** mostrar el valor de cada modelo disponible y **No disponible** para el que falló, sin inventar porcentajes.
- **Vacío:** explicar por qué no hay elementos y ofrecer la acción que permite empezar; en historial, volver a analizar.
- **Error recuperable:** mostrar causa comprensible y una acción concreta. En timeout tras enviar un análisis, orientar a revisar el historial antes de repetirlo.
- **Sesión pendiente de confirmación:** mantener visible el siguiente paso y no presentar la cuenta como activa ni perder la sesión invitada.

## Movimiento y accesibilidad

- Las animaciones (barrido, LEDs, barras, encendido) son decorativas. Ningún elemento parpadea más de 3 veces por segundo.
- Con `prefers-reduced-motion: reduce` se desactivan todas las animaciones y transiciones y desaparece el barrido del radar. Las barras quedan fijas.
- Foco de teclado: contorno amarillo `focus` de 2 px. En las teclas con chaflán se dibuja hacia dentro, y en las teclas cian o rojas es discontinuo y oscuro.
- Navegación por teclado, orden de foco lógico y nombres accesibles en los botones de icono. Los títulos en mayúsculas lo son solo por CSS, así que los lectores de pantalla leen el texto original.
- No usar rojo y verde como única diferencia: siempre van con etiqueta, valor y glifo.
- Comprobar cada cambio a 400 px de ancho, sin desplazamiento horizontal.
