# Plan general de desarrollo del frontend de ScanTrue

## Objetivo y límites

Desarrollar únicamente la interfaz de la extensión de Chrome/Chromium para analizar texto de noticias, consultar resultados e historial, gestionar la sesión del usuario y mostrar métricas. Todo el código, recursos, pruebas y documentación de esta etapa permanecerán dentro de `frontend/`.

Este plan parte de los prototipos de `Avance 2.docx` y usa `FRONTEND_CONTEXT.md` como referencia de integración, sin asumir que describa el estado definitivo de la API. mBERT ya está desarrollado; el frontend debe consumir su resultado real cuando el backend lo entregue. Los puntos que requieren respuesta o trabajo del backend están separados en `DEPENDENCIAS_BACKEND.md`.

## Tecnologías definidas

| Área | Tecnología y uso |
| --- | --- |
| Interfaz | **React** para el popup y las vistas de resultados de los modelos, historial, cuentas, métricas y detalle. |
| Estilos y diseño | **Tailwind CSS** para una interfaz adaptable y fácil de modificar, con componentes y estilos consistentes. |
| Integración con el navegador | **JavaScript nativo** para el content script, la extracción del texto de la página y el service worker de Manifest V3. |
| Comunicación | **API REST del backend FastAPI**. El frontend consumirá sus rutas y mostrará sus respuestas; FastAPI no forma parte del código de la extensión. |

## Decisiones iniciales para la primera versión

- Iniciar la selección explícita de texto con **Escoger texto** en el popup. El usuario revisa el fragmento en P02 y pulsa **Analizar** para iniciar la solicitud y pasar directamente a P04. La extracción automática de una noticia completa queda como decisión posterior.
- Usar Manifest V3 y mostrar todas las vistas dentro del popup, incluido el reporte, el historial y los detalles extensos. Resolver el espacio limitado con navegación interna y contenido desplazable.
- Separar la interfaz React de los scripts nativos del navegador. Definir la compilación para que Chrome cargue el popup, el content script y el service worker generados.
- Presentar las probabilidades como salidas de clasificadores, no como una comprobación de hechos. Mostrar BiLSTM, mBERT y el resultado unificado según los datos recibidos.

## Desarrollo paso a paso

### 1. Cerrar el alcance funcional y los recorridos

**Trabajo frontend:** definir los recorridos de invitado, usuario con cuenta, análisis, historial y métricas. Organizar todas las pantallas como vistas internas del popup y definir cómo se vuelve de cada una. Registrar los textos y estados visibles para cada recorrido.

**Resultado:** mapa de pantallas y lista de acciones por pantalla, incluyendo carga, vacío, éxito y error.

**Criterio de salida:** cada acción del usuario tiene una pantalla de origen, una respuesta esperada y un estado de error definido.

### 2. Definir el diseño visual y los componentes

**Trabajo frontend:** adaptar las vistas de escaneo, resultado, desglose, historial y reporte del prototipo. Diseñar además acceso, registro, confirmación de correo y detalle de historial. Aplicar `SISTEMA_DISENO.md` a cada pantalla; establecer componentes React reutilizables y reglas adaptables con Tailwind CSS para ventanas estrechas. Mantener las instrucciones iniciales breves y sin nombres técnicos de modelos.

**Resultado:** diseños o especificaciones de pantalla que puedan implementarse sin inventar estados durante la programación.

**Criterio de salida:** todas las pantallas del paso 1 tienen jerarquía visual, contenido y comportamiento de navegación definidos.

### 3. Preparar la base de la extensión

**Trabajo frontend:** crear dentro de `frontend/` el proyecto React con Tailwind CSS, el manifiesto, el service worker y el content script en JavaScript nativo, el popup con sus vistas internas, los recursos y los módulos de estado y API. Configurar la compilación y solo los permisos que exige el flujo aprobado.

**Resultado:** extensión cargable en modo desarrollador con navegación básica entre vistas.

**Criterio de salida:** Chrome carga la extensión sin errores y el popup abre correctamente.

### 4. Implementar la captura de selección

**Trabajo frontend:** conectar el botón **Escoger texto** con el content script en JavaScript nativo para obtener el fragmento elegido en la página. Recibir la selección y la URL, guardar el texto pendiente durante la sesión del navegador y mostrarlo en P02 para analizarlo o escoger otro. Validar que la URL enviada sea HTTP(S) y respetar el límite acordado con la API.

**Resultado:** recorrido completo desde una selección en una página hasta la pantalla previa al envío.

**Criterio de salida:** se conserva la selección aunque se reinicie el service worker y nunca se envía texto distinto del elegido por el usuario.

### 5. Implementar comunicación y estado de servicios

**Trabajo frontend:** centralizar las solicitudes REST al backend FastAPI, los tiempos de espera y el tratamiento de respuestas y errores. Consultar `/salud` para indicar disponibilidad. Mostrar un mensaje útil cuando la API local no esté encendida.

**Resultado:** un cliente de API reutilizable por todas las pantallas.

**Criterio de salida:** la interfaz distingue entre servicio inaccesible, respuesta HTTP de error y respuesta válida.

### 6. Implementar sesión de invitado y cuentas

**Trabajo frontend:** crear una sesión de invitado antes del primer análisis; conservarla entre reinicios, renovar tokens y limitar el acceso a esos datos a contextos confiables de la extensión. Construir registro, inicio de sesión, confirmación de correo y cierre de sesión. Preservar la sesión invitada hasta que el acceso a la cuenta y la incorporación de historial se confirmen.

**Resultado:** recorridos de autenticación y persistencia de sesión.

**Criterio de salida:** un invitado puede volver a abrir Chrome y consultar su historial; un error de acceso no borra su sesión recuperable.

### 7. Implementar análisis y resultado

**Trabajo frontend:** mostrar en P02 un aviso breve de que el texto se enviará y se guardará en el historial. Al pulsar **Analizar**, enviar la selección una sola vez y mostrar P04 sin otra pantalla intermedia. Después representar los valores recibidos para BiLSTM, mBERT y el resultado unificado. Mostrar modelos participantes y coincidencia o discrepancia. Para un modelo sin resultado válido, mostrar **No disponible**.

**Resultado:** pantalla de resultado conectada a la API.

**Criterio de salida:** los porcentajes provienen de la respuesta; la interfaz no fabrica una predicción de mBERT ni calcula por su cuenta el valor unificado. Después de un timeout no repite automáticamente la petición.

### 8. Implementar historial y detalle

**Trabajo frontend:** listar análisis propios con paginación, fecha y vista previa; abrir el detalle completo; permitir eliminación con confirmación. Resolver registros antiguos que no tengan texto, vista previa o algún resultado por modelo.

**Resultado:** historial navegable y detalle de cada análisis.

**Criterio de salida:** la lista y el detalle muestran los valores guardados originalmente; los estados vacíos y los registros no encontrados tienen mensajes claros.

### 9. Implementar métricas

**Trabajo frontend:** crear una vista de métricas de evaluación basada exclusivamente en los datos recibidos de `/metricas`. El registro de blockchain no se mostrará en el popup.

**Resultado:** reporte de métricas integrado.

**Criterio de salida:** las métricas se identifican como evaluación de modelos y no como resultados de una noticia concreta.

### 10. Completar errores, accesibilidad y seguridad de interfaz

**Trabajo frontend:** presentar mensajes legibles para validaciones de texto, sesión vencida, credenciales incorrectas, servicios no disponibles y fallos de guardado. Añadir navegación por teclado, foco visible, etiquetas accesibles y contraste adecuado. Revisar permisos, almacenamiento y registros de consola para evitar exponer tokens, contraseñas o selecciones.

**Resultado:** interfaz utilizable en condiciones normales y de fallo.

**Criterio de salida:** cada error previsto tiene una acción de recuperación y no se muestran objetos JSON crudos al usuario.

### 11. Verificar y preparar la entrega

**Trabajo frontend:** probar en Chrome los recorridos completos de invitado y cuenta, mBERT disponible y fallido, historial, eliminación, métricas y API desconectada. Revisar navegación, desplazamiento y legibilidad de todas las vistas en el popup, comprobar la compilación de React, Tailwind CSS y los scripts nativos, empaquetar la extensión y documentar instalación y uso local.

**Resultado:** versión de frontend lista para revisión.

**Criterio de salida:** los recorridos principales funcionan con respuestas reales de la API y no requieren cambios fuera de `frontend/` para cargar la extensión.

## Orden de ejecución y dependencias

Los pasos 1 y 2 fijan el producto; el paso 3 crea su base. Los pasos 4 y 5 permiten probar la captura y la conexión. La sesión del paso 6 precede al análisis protegido del paso 7. Historial y métricas siguen en los pasos 8 y 9. Los pasos 10 y 11 cierran la calidad y la entrega.

Las dudas o cambios necesarios del backend se registran en `DEPENDENCIAS_BACKEND.md`; no forman parte de la implementación del frontend.
