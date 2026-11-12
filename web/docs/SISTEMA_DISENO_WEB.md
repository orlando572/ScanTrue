# Sistema de diseño de la web de ScanTrue

## Dirección visual

La misma familia que la extensión ([`frontend/docs/SISTEMA_DISENO.md`](../../frontend/docs/SISTEMA_DISENO.md)) —interfaces de ciencia ficción retro de los 80 y 90, paneles técnicos de anime, gráficos vectoriales y HUD de varios colores—, pero **minimalista y con otra paleta**: negro puro, mucho aire y pocos paneles. La extensión es una consola cian sobre azul; la web es un campo vectorial violeta sobre negro.

- **Evitar:** tarjetas redondeadas y sombras suaves, degradados de fondo, y cualquier símbolo de «verificado».
- Las reglas de contenido de la extensión valen igual: «salida para falsa», nunca «certeza» ni «verídica»; siempre la aclaración de que es una orientación.

## Paleta

Tokens en `@theme` de `src/styles.css`.

| Token | Valor | Uso |
| --- | --- | --- |
| `void` | `#000000` | Fondo. |
| `panel` / `panel-2` | `#0A0A0C` / `#131318` | Paneles; campos y filas activas. |
| `line` / `line-2` | `#26262E` / `#3A3A46` | Bordes y segmentos apagados. |
| `ink` / `muted` | `#F2F2F5` / `#9A9AA8` | Texto principal y secundario. |
| `violet` | `#9B7CFF` | Acento de la web pública: acciones, marcos, BETO. |
| `acid` | `#E6FF4D` | Datos y contadores, página de origen, BiLSTM, foco de teclado. |
| `coral` | `#FF6A3D` | Acento de administración, índices de fragmento, verificación web. |

Un color por criterio: **BiLSTM** ácido, **BETO** violeta, **Verificación web** coral.

Los cinco niveles del resultado conservan los colores de la extensión, porque significan lo mismo: `#3DFF9A`, `#2EE6C8`, `#FFB21E`, `#FF7A1A`, `#FF4A3D` (clases `tone-*`). Siempre van con la etiqueta del nivel y el porcentaje; el color nunca es la única señal.

En `/admin` el acento (`--accent`) pasa de violeta a coral: se nota a primera vista que es otra zona.

## Tipografía

Las mismas tres familias, empaquetadas con `@fontsource`: **Orbitron** (marca y títulos, mayúsculas por CSS), **Share Tech Mono** (rótulos, cifras, botones) e **IBM Plex Sans** (lectura; los fragmentos van siempre en esta).

## Fondo interactivo

`src/components/VectorField.jsx`, un `<canvas>` fijo a pantalla completa, sin librerías:

- **Retícula en perspectiva** bajo un horizonte luminoso, que avanza despacio; el punto de fuga sigue un poco al puntero.
- **Constelación** de 28 a 90 nodos (según el tamaño de la pantalla) unidos por líneas. Cerca del puntero los nodos se apartan, se encienden en ácido y se conectan a una **mira** que gira.
- **Un clic** lanza una onda de radar coral que empuja los nodos a su paso.
- En páginas de lectura (todo menos Inicio) baja al 50 % de opacidad. Encima va una capa de líneas de escaneo y viñeta.
- Es decorativo (`aria-hidden`, `pointer-events: none`). Se detiene con la pestaña oculta, limita la densidad de píxeles a 2 y con `prefers-reduced-motion` dibuja un solo fotograma fijo, sin mira ni ondas.

## Componentes

| Elemento | Regla |
| --- | --- |
| Panel (`.panel`) | Opaco, borde de 1 px y dos esquinas cortadas de 14 px. `--edge` da color al borde (`panel--accent`, `panel--tone`); `panel--mark` añade una escuadra. |
| Botón (`.btn`) | Tecla con chaflán; principal con el acento y texto negro; `btn--ghost` gris; `btn--danger` rojo. Uno principal por vista. |
| Filtros (`Filters.jsx`) | Buscador con retardo de 350 ms, teclas de nivel con su color y desplegables. Los filtros viven en la URL, así que una búsqueda se puede compartir. |
| Tarjeta de resultado | Izquierda: código, fecha, página de origen y **solo los fragmentos** (`#01`, `#02`…; no hay título). Derecha: porcentaje y nivel, espectro, los tres criterios y estado. El borde toma el color del nivel. |
| Espectro (`Spectrum`) | Cinco zonas; BETO ▼ encima, BiLSTM ▲ debajo y el combinado como rombo. |
| Dial (`Dial`) | 40 segmentos en un arco de 270° que se encienden en orden. |
| Texto leído | En el detalle, cada modelo despliega el texto que leyó; lo que quedó fuera de su límite va en gris. |
| Carga (`Loader`) | Rótulo corto con cursor, barra recorrida por una luz y esqueleto; aparece con 150 ms de retraso. |

## Movimiento y accesibilidad

- Entrada en cascada de los bloques (`.boot`), contadores que cuentan, barras y segmentos que se trazan. Todo se desactiva con movimiento reducido.
- Foco de teclado: contorno ácido de 2 px. Navegación completa por teclado; los atajos de revisión no actúan mientras se escribe en un campo.
- Probado a 1440 px y a 390 px, sin desplazamiento horizontal.
