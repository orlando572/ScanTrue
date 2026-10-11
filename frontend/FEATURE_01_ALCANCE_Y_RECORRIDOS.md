# Feature 01: alcance funcional y recorridos del frontend

## Propósito

Definir con suficiente precisión la primera versión de la extensión ScanTrue antes de diseñar pantallas o escribir código. Este feature corresponde al paso 1 de `PLAN_FRONTEND.md` y cubre únicamente decisiones y entregables del frontend. Las confirmaciones de la API se mantienen en `DEPENDENCIAS_BACKEND.md`.

## Resultado esperado

Al terminar este feature deben estar acordados:

1. Las funciones incluidas en la primera versión y las que se posponen.
2. El mapa de pantallas y dónde se abre cada una.
3. Los recorridos de invitado y de usuario con cuenta.
4. Las acciones, respuestas y estados de error de cada pantalla.
5. Los textos esenciales que evitan interpretar una clasificación como verificación de hechos.

No se crearán componentes, estilos, manifiesto ni llamadas a la API durante este feature.

## Restricciones técnicas ya definidas

- Todas las pantallas se planificarán como vistas internas del **popup** en **React**, con estilos de **Tailwind CSS** adaptables al espacio disponible.
- La captura de texto, el content script y el service worker de **Manifest V3** se planificarán en **JavaScript nativo**.
- Las vistas consumirán la **API REST del backend FastAPI**. Este feature define la experiencia y los datos necesarios; no desarrolla ni modifica el backend.
- Todo entregable de frontend de este feature permanecerá dentro de `frontend/`.

## Propuesta de alcance para la primera versión

### Incluido

- Iniciar la captura desde **Escoger texto** en el popup y mostrar en P02 el fragmento que el usuario seleccione en la página.
- Mostrar la selección pendiente y permitir continuar, descartarla o elegir otra.
- Informar en P02, junto a **Analizar**, que el texto se enviará y se conservará en el historial del usuario.
- Crear y conservar una sesión de invitado; ofrecer registro, confirmación de correo, acceso y cierre de sesión.
- Analizar una selección y mostrar las salidas reales de BiLSTM y mBERT, el resultado unificado que entregue la API y el estado de comparación.
- Consultar historial propio, abrir un análisis anterior y eliminarlo con confirmación.
- Consultar métricas de evaluación publicadas.
- Explicar estados de indisponibilidad, validación y sesión sin mostrar errores técnicos crudos.

### Pospuesto

- Extraer automáticamente el contenido principal de una página o analizarla sin selección explícita.
- Analizar imágenes, audio o video.
- Modificar contenido de páginas visitadas o mostrar etiquetas superpuestas sobre ellas.
- Compartir resultados, exportar reportes o mostrar la trazabilidad blockchain.
- Crear porcentajes, clasificaciones adicionales o datos de métricas que la API no proporcione.

La selección manual es una **decisión propuesta para este feature**. Si se decide incluir extracción automática, hay que revisar el mapa de permisos, la captura y los estados antes del paso 3 del plan general.

## Usuarios y superficies

| Actor o superficie | Necesidad principal | Límite de este feature |
| --- | --- | --- |
| Visitante sin sesión local | Analizar una selección sin crear cuenta | La extensión prepara una sesión invitada antes de enviar el análisis. |
| Invitado recurrente | Recuperar sus análisis al volver a abrir Chrome | La sesión invitada y el historial propio deben seguir disponibles. |
| Usuario con cuenta | Entrar, consultar historial y cerrar sesión | La transición desde invitado no debe perder registros recuperables. |
| Popup | Iniciar y completar todos los recorridos, incluido historial, detalle, métricas y cuenta | Las vistas extensas deben tener navegación clara y desplazamiento interno sin abrir páginas adicionales. |

## Mapa propuesto de pantallas

| ID | Pantalla | Superficie propuesta | Acciones principales |
| --- | --- | --- | --- |
| P01 | Inicio y estado del servicio | Popup | Ver disponibilidad, elegir texto, abrir historial o cuenta. |
| P02 | Selección pendiente | Popup | Revisar fragmento, analizar, descartar, elegir otro. |
| P04 | Análisis en curso | Popup | Ver el estado de espera y recibir una respuesta, sin progreso inventado. |
| P05 | Resultado | Popup | Leer unificado y modelos, abrir desglose o historial. |
| P06 | Desglose por modelo | Popup | Leer BiLSTM, mBERT y la comparación disponible. |
| P07 | Historial | Popup | Abrir detalle y cargar más resultados. |
| P08 | Detalle del historial | Popup | Leer selección y resultados guardados; eliminar con confirmación. |
| P09 | Métricas de evaluación | Popup | Leer conjuntos, medidas y limitaciones. |
| P11 | Cuenta | Popup | Elegir registro, acceso o cierre de sesión. |
| P12 | Registro y confirmación | Popup | Crear cuenta, leer estado de confirmación, volver a acceder. |
| P13 | Inicio de sesión | Popup | Entrar, mostrar errores y resultado de incorporación de historial. |

Todas las pantallas incluidas (P01, P02, P04 a P09 y P11 a P13) permanecen dentro del popup. P03 y P10 se eliminan; se conservan los demás identificadores para no romper las referencias existentes.

## Recorridos principales

### R01. Primer análisis como invitado

1. El usuario pulsa **Escoger texto** en P01 y selecciona un fragmento en la página.
2. La extensión muestra P02 con el fragmento recibido. Si el popup no se abre automáticamente, conserva la selección pendiente para mostrarla al abrirlo desde el icono.
3. P02 informa de forma breve que el texto se enviará y guardará en el historial. El usuario pulsa **Analizar** o **Seleccionar de nuevo**.
4. Al pulsar **Analizar**, la extensión prepara la sesión invitada, inicia una sola solicitud y muestra P04 mientras espera la respuesta.
5. P05 muestra el valor unificado, BiLSTM, mBERT y los estados recibidos. P06 ofrece el desglose.
6. El usuario puede abrir P07 o iniciar otro análisis.

**Alternativas:** sin selección, texto rechazado, API inaccesible, sesión no disponible, modelo indisponible, fallo de guardado y timeout. En un timeout no se ofrece una repetición automática; se orienta a revisar el historial.

### R02. Volver como invitado

1. El usuario abre la extensión después de reiniciar Chrome.
2. P01 reconoce la sesión guardada o presenta una acción para recuperarse si venció.
3. Desde P07 consulta sus análisis anteriores y abre P08.

**Alternativas:** sesión caducada que puede renovarse; renovación fallida que requiere una nueva sesión o acceso a cuenta sin borrar silenciosamente datos recuperables.

### R03. Crear cuenta desde invitado

1. Desde P11 el invitado abre P12 y envía correo y contraseña.
2. Si la cuenta queda pendiente de confirmación, P12 explica el siguiente paso y la extensión mantiene intacta la sesión invitada.
3. Tras confirmar el correo, el usuario vuelve a P13 e inicia sesión.
4. La interfaz informa cuántos registros invitados se incorporaron, si la API entrega ese dato.

**Alternativas:** correo inválido, cuenta existente, servicio de autenticación no disponible o incorporación fallida. Ninguno de estos estados debe aparentar que el historial se transfirió cuando no hay confirmación.

### R04. Iniciar y cerrar sesión

1. Un usuario existente entra desde P13; si conserva una sesión invitada con historial, se solicita la incorporación según el contrato confirmado.
2. P11 muestra el estado de cuenta y permite cerrar sesión.
3. Al cerrar, la interfaz vuelve a un estado sin cuenta y habilita el flujo de invitado para el siguiente análisis.

**Alternativas:** credenciales incorrectas, confirmación pendiente, sesión vencida y error del servicio.

### R05. Consultar y eliminar historial

1. Desde P01 o P05, el usuario abre P07.
2. Selecciona una fila para abrir P08, con el texto y los resultados guardados disponibles.
3. Si elige eliminar, ve una confirmación de la eliminación del elemento de su historial.
4. Tras una eliminación exitosa, P07 actualiza la lista.

**Alternativas:** historial vacío, datos antiguos sin texto o vista previa, carga fallida, registro inexistente o ajeno, eliminación fallida.

### R06. Consultar métricas

1. Desde P01 se abre P09 para consultar evaluaciones de modelos. La vista identifica versión, conjunto y limitaciones.

**Alternativas:** métricas no disponibles o carga fallida.

## Estados que debe contemplar cada pantalla

| Grupo | Estados mínimos | Respuesta visible esperada |
| --- | --- | --- |
| Carga | Inicial, cargando, éxito | Indicar qué operación está en curso; impedir envíos duplicados. |
| Contenido | Con datos, sin datos, datos parciales | Mostrar valores presentes y explicar los ausentes. |
| Conectividad | API disponible, degradada, inaccesible | Indicar disponibilidad y una acción de reintento cuando corresponda. |
| Texto | Pendiente, vacío, insuficiente, ilegible, demasiado largo | Conservar o descartar la selección y explicar cómo corregirla. |
| Sesión | Invitado, cuenta, pendiente de confirmación, vencida, error | Mantener el recorrido recuperable y mostrar la siguiente acción. |
| Modelos | Ambos disponibles, solo uno, ninguno | Mostrar porcentajes únicamente de modelos con respuesta válida. |
| Análisis | En curso, completado, timeout, error de guardado | Evitar doble envío tras un timeout y orientar al historial. |

## Mensajes esenciales a definir en el paso 2

- Aviso breve en P02: el texto seleccionado y la URL, si corresponde, se envían para el análisis y el texto se guarda en el historial propio.
- Etiqueta de los porcentajes: **salida para falsa**; una salida de clasificación no confirma la veracidad de una noticia.
- Modelo no disponible: **No disponible**, con explicación breve cuando exista.
- Timeout: el análisis pudo haberse guardado; consultar historial antes de intentar enviarlo otra vez.
- Métricas: corresponden a conjuntos de evaluación del modelo, no a la noticia abierta ni al uso de la extensión.

## Tareas para completar este feature

1. **Cerrar el alcance:** revisar las funciones incluidas y pospuestas; decidir si la selección manual es el único método de captura de la primera versión. Entregable: lista de alcance acordada.
2. **Fijar navegación:** definir las transiciones, el regreso y el desplazamiento de P01, P02, P04 a P09 y P11 a P13 dentro del popup. Entregable: mapa de vistas y navegación del popup.
3. **Validar recorridos:** recorrer R01 a R06 en orden y comprobar que cada acción tenga destino, salida exitosa y alternativa de error. Entregable: recorridos sin pasos ambiguos.
4. **Completar estados:** revisar la tabla de estados contra los prototipos y los ejemplos reales de la API cuando estén disponibles. Entregable: matriz de estados por pantalla, con carga, vacío y recuperación donde corresponda.
5. **Acordar mensajes:** aprobar el sentido de los avisos de privacidad, clasificación, métricas y timeout antes de redactar el texto final de la interfaz. Entregable: mensajes esenciales aprobados.
6. **Registrar dependencias:** marcar cualquier dato faltante de la API en `DEPENDENCIAS_BACKEND.md`, sin resolverlo con datos simulados como comportamiento definitivo. Entregable: lista de confirmaciones pendientes para la integración.

## Criterios de aceptación del feature

- El alcance incluido y pospuesto está aprobado para la primera versión.
- P01, P02, P04 a P09 y P11 a P13 tienen ubicación, propósito y acciones definidos.
- R01 a R06 pueden recorrerse sin saltos ni callejones sin salida.
- Cada acción tiene al menos una respuesta de éxito, un estado de carga cuando aplica y una salida de error o recuperación.
- Se distinguen sesión invitada y cuenta, y se muestran los resultados de los modelos sin datos de blockchain en el popup.
- Ninguna pantalla promete verificar hechos, calcula un porcentaje propio o presenta métricas inventadas.
- Las dudas del backend están separadas en `DEPENDENCIAS_BACKEND.md`.

## Decisiones aún abiertas

1. Confirmar selección manual como único método de captura inicial o ampliar a extracción automática.
2. Definir cómo se mostrará contenido extenso en P06, P07, P08, P09 y P11 dentro del popup sin perder legibilidad.
3. Confirmar los nombres y la forma final de los campos recibidos para mBERT y el resultado unificado. Esto depende de la API y se registra en `DEPENDENCIAS_BACKEND.md`.

Las decisiones 1 y 2 son de producto/frontend. La decisión 3 no bloquea el mapa de recorridos, pero sí el detalle final de contenido y la integración.
