# ScanTrue frontend

Base de la extensión Chrome/Chromium Manifest V3. El popup usa React y Tailwind CSS; el content script y el service worker están escritos en JavaScript nativo. Las pantallas se completarán una por una según sus planes dentro de esta carpeta.

## Preparar y compilar

Se necesita Node.js 20.19 o superior compatible con `package.json`.

```powershell
cd D:\ScanTrue\frontend
npm install
npm run build
```

La compilación genera `dist/` con `manifest.json`, `popup.html`, recursos locales y `extension/service-worker.js` y `extension/content-script.js`. `dist/` se vuelve a crear al compilar y no se edita directamente.

## Cargar en Chrome

1. Abrir `chrome://extensions` y activar el modo de desarrollador.
2. Elegir **Cargar descomprimida** y seleccionar `D:\ScanTrue\frontend\dist`.
3. Abrir el icono ScanTrue. P01 muestra el estado real de `/salud`, permite navegar dentro del popup e inicia la selección de texto en la pestaña activa.

Después de volver a compilar, pulsar **Recargar** en la tarjeta de ScanTrue dentro de `chrome://extensions` y cerrar cualquier popup anterior antes de abrirlo de nuevo. Si solo aparece «Abriendo el popup…», abrir **Inspeccionar vistas → popup** desde esa tarjeta y revisar el primer error de la consola; el mensaje de respaldo indica que el código de React no terminó de cargar.

Tras pulsar **Escoger texto**, seleccionar un fragmento de una página HTTP(S) y volver a abrir el popup. P02 muestra el texto completo, permite **Seleccionar de nuevo** sin perder el fragmento anterior y envía el análisis solo al pulsar **Analizar**. La extensión crea o renueva una sesión invitada y envía el texto a la API local. P04 muestra la espera, la demora prolongada y los estados de recuperación sin reenvíos automáticos. P05 muestra la salida unificada recibida, la participación de modelos y su comparación cuando está disponible. P06 muestra las salidas individuales de BiLSTM y mBERT. P07 lista el historial de la sesión activa y P08 abre su detalle guardado. P09 muestra las métricas publicadas por la API. P11 muestra el estado de cuenta y permite cerrar una sesión de cuenta confirmada. P12 y P13 permiten registrarse e iniciar sesión mediante la API local. Las dependencias que deben confirmar desde backend están en `DEPENDENCIAS_BACKEND.md`.

El registro usa una sesión invitada. Si el backend solicita confirmación por correo, la extensión conserva esa sesión y su historial hasta que el usuario confirme el correo y vuelva a iniciar sesión. El inicio envía el token invitado para incorporar los análisis a la cuenta; los tokens locales se sustituyen solo después de recibir una sesión de cuenta válida. Si la sesión invitada ya no puede renovarse, la pantalla permite entrar sin transferir su historial únicamente tras una elección explícita. El backend y Supabase deben estar disponibles para estos recorridos.

Para comprobar P02, recargar la extensión, abrir una página HTTP(S), pulsar **Escoger texto**, marcar un fragmento y reabrir el popup. Probar **Seleccionar de nuevo** antes de pulsar **Analizar**; para esta última acción debe estar disponible la API local en `127.0.0.1:8000`.

Para comprobar P04, pulsar **Analizar** y observar el estado de espera. Cerrar y reabrir el popup durante la solicitud no debe iniciar otra. Un texto rechazado regresa a P02; una respuesta válida llega a P05. Si el resultado queda incierto, P04 ofrece **Revisar historial**, que abre P07.

Para comprobar P05, usar una respuesta de la API que incluya `resultado_unificado.probabilidad_falsa` y `modelos_utilizados`. La pantalla muestra el porcentaje recibido y, con dos modelos, la coincidencia o discrepancia informada. Si falta unificado, indica que no está disponible. **Escoger otro texto** limpia la operación completada y vuelve a P01.

Para comprobar P06, pulsar **Ver desglose por modelo** en P05. BiLSTM y mBERT aparecen en ese orden; cada porcentaje solo se muestra si su estado es `ok` y la probabilidad es válida. **Volver** regresa al mismo resultado de P05 sin solicitar otro análisis.

Para comprobar P07, abrir **Historial** desde la cabecera. La extensión consulta `GET /analisis?limit=20&offset=0` con la sesión activa, muestra los datos guardados y permite cargar más páginas. Acepta una lista JSON o un objeto con `items`, `analisis` o `registros`; utiliza `total`, `hay_mas` o `has_more` si la respuesta los incluye. Este formato de paginación requiere confirmación del backend. Al elegir una fila se abre P08; **Volver** conserva la lista y su posición.

Para comprobar P08, elegir un registro del historial. La extensión consulta `GET /analisis/{id}` y muestra el texto y resultado almacenados. **Ver desglose por modelo** abre P06 con ese registro y regresa a P08. **Eliminar análisis** requiere una segunda confirmación; la fila solo se retira de P07 cuando `DELETE /analisis/{id}` responde `{ "eliminado": true }`. Un fallo conserva la vista y permite reintentar.

Para comprobar P09, abrir **Métricas de modelos** desde P01. La extensión consulta `GET /metricas` sin sesión, muestra cada conjunto recibido y permite desplegar las medidas adicionales que estén disponibles. Una respuesta vacía muestra el estado correspondiente; un fallo permite reintentar. La forma definitiva de `/metricas` y sus limitaciones deben confirmarse con una respuesta real del backend.

Para comprobar P11, abrir **Cuenta** desde la cabecera. La pantalla distingue la sesión invitada, una cuenta iniciada, la confirmación pendiente y una sesión que no se pudo renovar. Los accesos **Iniciar sesión** y **Crear cuenta** abren las vistas todavía provisionales P13 y P12. Para una cuenta activa, **Cerrar sesión** llama `POST /sesiones/cerrar` y solo cambia la vista cuando la API confirma `{ "cerrada": true }`; un fallo conserva la sesión local. La respuesta real de cierre y los datos de cuenta todavía requieren confirmación del backend.
