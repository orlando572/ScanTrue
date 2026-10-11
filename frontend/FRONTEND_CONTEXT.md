# ScanTrue: contexto de integración para la extensión

Este documento está dirigido a quien implementará el frontend. Define el contrato de integración y las diferencias con el prototipo. La API y Anvil se ejecutan en el mismo equipo que Chrome; Supabase está alojado. La documentación interactiva de la API local está en `http://127.0.0.1:8000/docs` cuando el backend está encendido.

## Disponibilidad

| Etapa | Contrato |
| --- | --- |
| API actual | `POST /analisis` entrega `probabilidad_falsa` del BiLSTM y el estado de mBERT. Invitados, cuentas, historial, métricas y verificación blockchain tienen rutas implementadas. |
| Próxima entrega del backend | `resultado_unificado` en análisis e historial, `vista_previa` en el listado, `texto` en el detalle y `POST /sesiones/cerrar`. |
| mBERT real | Su `probabilidad_falsa` aparecerá cuando existan checkpoint, tokenizador y evaluación. |

El contrato de abajo permite preparar la interfaz de la próxima entrega. La configuración del proyecto Supabase, incluida la activación de Auth anónimo, corresponde al backend.

## Capacidades que debe usar el frontend

| Área | Comportamiento de la extensión |
| --- | --- |
| BiLSTM y `POST /analisis` | Modelo `pequeno_mejorado_fasttext_cc300_s42`; mínimo 100 y máximo 192 tokens medidos por el backend. |
| mBERT | Mostrar su porcentaje solo si `estado: "ok"`; cuando no haya checkpoint o falle, mostrar “No disponible”. Nunca fabricar una predicción. |
| Porcentaje unificado | Mostrar `resultado_unificado.probabilidad_falsa` en P05. Con solo BiLSTM coincide con su porcentaje; con ambos usa los pesos informados por la API. |
| Invitados, cuentas e historial | Mantener la sesión invitada y permitir abrir la selección completa desde el historial propio. |
| Métricas | `GET /metricas` publica evaluaciones del BiLSTM, no estadísticas de uso. |
| Blockchain | Un análisis puede estar pendiente antes de que Anvil confirme la transacción. |

Para conectar la extensión, usar `/salud` para mostrar la disponibilidad de los servicios. `supabase_configurado: true` indica configuración local, no el estado de cada proveedor de Auth.

## Comportamiento de la extensión

La primera versión será una extensión Manifest V3 para **Chrome/Chromium 127 o posterior**. El usuario selecciona un fragmento de la página y elige **“Analizar selección”** en el menú contextual. El fragmento puede incluir titular y cuerpo: se envía **como un solo `texto`**. No se separa el titular, no se extrae automáticamente el resto de la página y no se envía un segundo campo `titulo` en este flujo. Se adjunta la URL de la página como referencia cuando sea una URL HTTP(S) de hasta 2048 caracteres; la API no visita esa dirección.

El service worker recibe `selectionText` y `pageUrl`, prepara la solicitud y abre el popup del prototipo. Si Chrome no abre el popup automáticamente, conserva la selección pendiente y pide abrirlo desde el icono de la extensión. El botón de “Escoger texto a analizar” del prototipo puede guiar al usuario a seleccionar texto y usar el menú contextual. [Chrome documenta `selectionText` y `pageUrl`](https://developer.chrome.com/docs/extensions/reference/api/contextMenus) y [`action.openPopup()`](https://developer.chrome.com/docs/extensions/reference/api/action).

Usar como referencia visual las vistas de `backend/Avance 2.docx`: escaneo, resultado, desglose por modelo, historial y reporte. El reporte puede ocupar una página propia de la extensión si no cabe en el popup. Añadir vistas de invitado/cuenta, confirmación de correo, detalle del historial y verificación blockchain siguiendo ese lenguaje visual.

### Comunicación y sesión

- Base local inicial: `http://127.0.0.1:8000`. El service worker o una página de la extensión hace las solicitudes con permiso de host **solo** para esa API. No realizar solicitudes desde código inyectado en páginas ni pedir permisos generales sobre todos los sitios para capturar texto. [Chrome: solicitudes entre orígenes](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests).
- Las rutas protegidas reciben `Authorization: Bearer <access_token>`. La extensión no necesita claves de Supabase: **nunca** incluir `SUPABASE_SECRET_KEY`, la clave publicable ni la clave de Anvil en su paquete.
- Crear un invitado cuando no exista sesión. Conservar `access_token`, `refresh_token`, `usuario_id`, `anonimo` y la hora de vencimiento calculada a partir de `expires_in`. Renovar antes de vencer o una sola vez tras un `401` de sesión; guardar juntos los nuevos tokens.
- La sesión invitada debe sobrevivir al reinicio de Chrome. Guardar tokens en `chrome.storage.local` y restringir ese almacenamiento a `TRUSTED_CONTEXTS`; no exponerlos a content scripts. Guardar el texto seleccionado pendiente solo en `chrome.storage.session`, y retirarlo al terminar. El service worker de Manifest V3 puede detenerse, por lo que su memoria no es fuente persistente de sesión. [Chrome: almacenamiento](https://developer.chrome.com/docs/extensions/reference/api/storage), [ciclo de vida](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).
- El texto seleccionado y su URL se enviarán a la API; el texto quedará almacenado en Supabase para el historial del propietario. Informar esto al usuario antes del primer análisis. No poner tokens, contraseñas ni contenido seleccionado en logs de producción.

## Rutas de integración

Las formas de respuesta de esta sección incluyen los campos de la próxima entrega indicados en la tabla de disponibilidad.

| Método y ruta | Autorización | Uso y respuesta principal |
| --- | --- | --- |
| `GET /salud` | Pública | `estado`, disponibilidad de modelos, configuración de Supabase y conexión con Anvil. Puede responder `degradado` con HTTP 200. |
| `POST /invitados` | Pública | Crea sesión anónima: `usuario_id`, `anonimo`, `access_token`, `refresh_token`, `expires_in`. |
| `POST /cuentas` | Invitado, Bearer | Cuerpo `{correo, contrasena}`. Responde `estado: "activa"` con `sesion`, o `estado: "pendiente_confirmacion"` con `sesion: null`. Incluye `registros_incorporados`. |
| `POST /sesiones` | Pública | Cuerpo `{correo, contrasena}`. Para incorporar el historial invitado, añadir `X-Guest-Token: <access_token_del_invitado>`. Devuelve `sesion` y `registros_incorporados`. |
| `POST /sesiones/renovar` | Pública | Cuerpo `{refresh_token}`. Devuelve una sesión con nuevos tokens. |
| `POST /sesiones/cerrar` | Bearer | Cierra la sesión actual y responde `{ "cerrada": true }`. |
| `POST /analisis` | Bearer | Cuerpo `{texto, url}`. Devuelve resultado, `id` y `estado_blockchain: "pendiente"`; no espera la confirmación de Anvil. |
| `GET /analisis?limit=20&offset=0` | Bearer | Lista el historial propio con `vista_previa` y `resultado_unificado`, ordenado del más reciente. `limit` admite 1–100; `offset` empieza en 0. |
| `GET /analisis/{id}` | Bearer | Detalle de un análisis propio, con `texto` completo y `resultado_unificado`. Un ID ajeno o inexistente devuelve 404. |
| `DELETE /analisis/{id}` | Bearer | Elimina un análisis propio y responde `{ "eliminado": true }`. Un ID ajeno o inexistente devuelve 404. |
| `GET /analisis/{id}/verificacion` | Bearer | Estado y comprobación del registro local; exige que el análisis pertenezca al solicitante. |
| `GET /metricas` | Pública | Evaluaciones publicadas del checkpoint BiLSTM; no exige sesión. |

### Análisis: petición y respuesta

Petición desde una selección (sin `titulo` separado):

```json
{
  "texto": "Fragmento completo seleccionado por el usuario, con titular y cuerpo si ambos están en la selección.",
  "url": "https://ejemplo.org/noticia"
}
```

La respuesta acordada tendrá esta forma; los valores son ilustrativos:

```json
{
  "id": "d7b9b1fb-0b62-4c4a-960e-5590cd43dd70",
  "resultados": {
    "bilstm": {
      "modelo": "bilstm",
      "estado": "ok",
      "version": "pequeno_mejorado_fasttext_cc300_s42",
      "clase": "falsa",
      "probabilidad_falsa": 0.73,
      "tokens_leidos": 120,
      "error": null
    },
    "mbert": {
      "modelo": "mbert",
      "estado": "no_disponible",
      "version": null,
      "clase": null,
      "probabilidad_falsa": null,
      "tokens_leidos": null,
      "error": "No se ha configurado el checkpoint y tokenizador de mBERT."
    }
  },
  "resultado_unificado": {
    "probabilidad_falsa": 0.73,
    "modelos_utilizados": ["bilstm"],
    "pesos_aplicados": {"bilstm": 1.0, "mbert": 0.0},
    "version_regla": "media_ponderada_v1"
  },
  "comparacion": "no_disponible",
  "nota": "Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
  "estado_blockchain": "pendiente"
}
```

Presentar el unificado en P05 y las salidas individuales de **BiLSTM** y **mBERT** en P06. Cada `probabilidad_falsa` va de 0 a 1; multiplicar por 100 para mostrar el porcentaje. La escala significa 0 % = el modelo favorece “real” y 100 % = favorece “falsa”. Son **salidas de clasificación, no certeza factual**: el porcentaje se acompaña de uno de cinco niveles visuales y se evita “certeza” o “veracidad comprobada”. Para un modelo con `estado` distinto de `ok`, mostrar “No disponible” en lugar de 0 %. No calcular el unificado en el frontend: usar `resultado_unificado` del backend.

El backend calculará una media ponderada: mBERT 70 % y BiLSTM 30 % cuando ambos respondan; los pesos podrán cambiar en la configuración del backend. Si solo uno responde, su peso aplicado será 100 %. `comparacion` será `coinciden` o `discrepan` únicamente con dos predicciones reales; de lo contrario será `no_disponible`. La interfaz actual muestra cinco niveles visuales según el porcentaje de P05 y de cada modelo en P06; no muestra mensajes de comparación entre modelos. Estos niveles son una interpretación de la salida, no una verificación de hechos.

El backend cuenta tokens con el tokenizador del BiLSTM **sobre el texto final enviado al modelo**. El frontend puede dar una orientación aproximada, pero debe tomar el `422` de la API como decisión definitiva. El mínimo de 100 tokens es una regla operativa y no una garantía de mayor precisión.

### Historial y verificación

Cada elemento del listado incluirá `id`, `fecha` (fecha ISO con zona horaria), `titulo` nullable, `url` nullable, `hash_texto`, `comparacion`, `estado_blockchain`, `hash_transaccion` nullable, `resultados`, `resultado_unificado` y `vista_previa`. El detalle incorporará además `texto` con la selección completa. En historial solo se guardan modelos que produjeron predicción; puede faltar la clave `mbert` aunque la respuesta inicial la haya mostrado como `no_disponible`. La extensión no envía `titulo` separado: identificar filas por la vista previa cuando exista, o por URL/dominio y fecha. Los análisis antiguos pueden tener `texto: null` y `vista_previa: null`; no reconstruirlos desde `hash_texto`.

El valor unificado y los pesos aplicados se guardarán con cada análisis. Si la configuración del backend cambia, los porcentajes de análisis anteriores conservarán su valor original.

Respuesta de verificación:

```json
{
  "estado_blockchain": "pendiente",
  "hash_transaccion": null,
  "verificado": null,
  "detalle": "registro_pendiente"
}
```

`estado_blockchain` puede ser `no_iniciado`, `pendiente`, `confirmado` o `fallido`. `verificado` puede ser `true`, `false` o `null`; **`null` no significa falso**. Consultar de nuevo mientras se muestra un estado pendiente y ofrecer actualización manual si Anvil está apagado. El registro blockchain es experimental y local: no presentar un explorador público ni afirmar que la cadena demuestra la veracidad de la noticia. Eliminar el historial no borra una transacción ya confirmada.

### Cuentas y confirmación

1. Crear y conservar una sesión de invitado antes de analizar.
2. Para registro, enviar `/cuentas` con el Bearer invitado. Si responde `pendiente_confirmacion`, **mantener intactos** sus tokens y su historial mientras se confirma el correo. Después, volver a la extensión e iniciar sesión con `/sesiones` y `X-Guest-Token`.
3. Para entrar a una cuenta existente, enviar `/sesiones` con el token invitado opcional si hay historial que incorporar. Reemplazar la sesión local por la de cuenta solo cuando el inicio y la incorporación hayan respondido correctamente.
4. Mostrar `registros_incorporados` como información de la transferencia. No enviar contraseña ni tokens a páginas visitadas.

Para cerrar sesión, llamar `POST /sesiones/cerrar` con el Bearer actual y retirar los tokens locales al obtener la respuesta. La operación revocará el token de renovación de esa sesión; un JWT de acceso ya emitido puede seguir válido hasta vencer. [Supabase: cierre de sesión](https://supabase.com/docs/guides/auth/signout).

## Métricas y adaptación del prototipo

`GET /metricas` devuelve `modelo: "bilstm"`, `version`, `orden_clases: ["falsa", "real"]`, `evaluaciones` y `limitaciones`. Cada evaluación contiene `conjunto`, `n`, `matriz_confusion`, `exactitud`, `precision_falsa`, `recall_falsa`, `f1_falsa`, `f1_macro` y `fuente`. Las filas de la matriz son las etiquetas reales y las columnas las predicciones, en el orden de `orden_clases`. Los valores corresponden a conjuntos de evaluación del modelo, **no al historial de usuarios ni a una tasa de acierto de la noticia abierta**.

La pantalla de reporte del prototipo contiene análisis totales, errores reportados y tiempos medios que la API no proporciona. No usarlos como datos reales. Mostrar únicamente los campos recibidos de `/metricas`, junto con su versión, conjunto y limitaciones. En resultado e historial, mostrar los tres espacios de porcentaje descritos arriba y atribuir las salidas a los modelos.

## Errores y estados de interfaz

| Respuesta o situación | Tratamiento en el frontend |
| --- | --- |
| `422` con `detail.codigo` como `texto_vacio`, `texto_ilegible`, `texto_insuficiente` o `texto_demasiado_largo` | Mostrar `detail.mensaje` y `detail.como_corregir`; dejar que el usuario seleccione otro fragmento. Otros `422` de validación pueden traer `detail` como lista. |
| `401` con `sesion_requerida` o `sesion_invalida` | Renovar la sesión una sola vez cuando sea posible. Si falla, solicitar nueva sesión o acceso a cuenta sin borrar silenciosamente el historial invitado recuperable. |
| `401` con `credenciales_invalidas` | Mantener el formulario de acceso y mostrar el error, sin renovar automáticamente por este motivo. |
| `404` al abrir, verificar o eliminar un ID | Mostrar que el registro no existe o no pertenece a la sesión actual. |
| `502` con `supabase_rechazo_operacion` | Mostrar que el historial no pudo completarse; no asumir que la predicción quedó guardada. |
| `503` por modelo, Auth, datos o `invitados_no_disponibles` | Mostrar indisponibilidad específica y la opción de reintentar si `detail.reintentar` lo indica. |
| API local inaccesible | Indicar que la API debe estar encendida en este equipo; conservar la selección pendiente durante la sesión del navegador. |
| Timeout después de enviar `POST /analisis` | **No repetir automáticamente**: el análisis pudo haberse guardado aunque se perdiera la respuesta. Consultar el historial antes de permitir otro envío. |

Los errores de la aplicación suelen tener `{ "detail": { "codigo": "...", "mensaje": "..." } }`; algunas respuestas HTTP estándar usan `detail` como texto o lista. La interfaz debe aceptar esas variantes sin mostrar un objeto JSON crudo.

## Criterios para integrar

- El frontend funciona con el backend local y no depende de una predicción mBERT ficticia.
- La selección íntegra se envía una sola vez; el backend decide si cumple 100–192 tokens.
- Invitado y cuenta ven solo su propio historial; se preserva el invitado durante la confirmación de correo y la transferencia.
- Los estados de blockchain y `verificado` se interpretan por separado.
- Los porcentajes de P05 y P06 muestran valores de la API; mBERT indica “No disponible” mientras no produzca una predicción real. P06 acompaña cada porcentaje individual con su etiqueta de nivel.
- Ninguna clave privilegiada, token ni texto seleccionado aparece en el código publicado o en los logs de la extensión.
