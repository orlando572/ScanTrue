# Dependencias y confirmaciones solicitadas al backend

Este archivo reúne únicamente lo que el frontend necesita conocer o recibir del backend. No asigna trabajo de backend al desarrollo del frontend. `FRONTEND_CONTEXT.md` es la referencia inicial, pero sus apartados sobre entregas futuras pueden haber cambiado. El equipo indicó que mBERT ya está desarrollado; falta confirmar su disponibilidad a través de la API.

## 1. Estado real de los endpoints

Confirmar cuáles de estas rutas están disponibles ahora y compartir ejemplos actuales de éxito y error: `/salud`, `/invitados`, `/cuentas`, `/sesiones`, `/sesiones/renovar`, `/sesiones/cerrar`, `/analisis`, `/analisis/{id}` y `/metricas`. Indicar si las rutas, métodos, parámetros o requisitos de autorización cambiaron respecto de `FRONTEND_CONTEXT.md`.

**Necesario antes de:** integrar pantallas con la API y cerrar las pruebas de extremo a extremo.

## 2. Predicción real de mBERT

Confirmar que el modelo desarrollado está cargado en el servicio usado por la extensión y mostrar una respuesta real de `POST /analisis` donde `resultados.mbert.estado` sea `ok` y exista `probabilidad_falsa`. Precisar cómo se informa un fallo o indisponibilidad de mBERT en una solicitud concreta.

**Necesario antes de:** validar la pantalla de desglose y los casos de mBERT disponible y no disponible.

## 3. Resultado unificado y comparación

Confirmar si la API entrega `resultado_unificado`, `modelos_utilizados`, `pesos_aplicados` y `comparacion` tanto en el análisis nuevo como en el historial y su detalle. Aclarar qué ocurre cuando solo responde uno de los modelos y si los resultados históricos conservan el valor calculado en su momento.

**Necesario antes de:** finalizar resultado e historial. El frontend mostrará estos datos; no definirá pesos ni calculará el unificado.

## 4. Validación del texto

Confirmar límites vigentes de longitud y tokens, y compartir respuestas `422` para texto vacío, ilegible, insuficiente y demasiado largo. Precisar si se admite `url: null` y el tamaño máximo de URL.

**Necesario antes de:** redactar ayudas de captura y mensajes de corrección. La API conserva la decisión definitiva de validez.

## 5. Sesiones e incorporación de historial invitado

Confirmar el flujo actual de invitado, renovación, registro, confirmación de correo, inicio, incorporación de registros y cierre de sesión. Aclarar las respuestas que preservan la sesión invitada y cuándo se puede sustituir con seguridad por la sesión de cuenta.

**Necesario antes de:** completar los recorridos de cuenta y probar que no se pierda el historial invitado.

## 6. Datos del historial

Confirmar los campos de listado y detalle, especialmente `vista_previa`, `texto`, `resultados`, `resultado_unificado`, fechas y paginación. Indicar cómo se representan registros anteriores que carezcan de esos campos y el comportamiento de IDs inexistentes o ajenos.

**Necesario antes de:** cerrar lista, detalle y eliminación.

## 7. Métricas

Compartir una respuesta real de `/metricas` con su versión, conjuntos evaluados y limitaciones. Los datos de blockchain no se requieren para el popup.

**Necesario antes de:** validar el reporte de métricas.

## 8. Entorno de integración

Confirmar la dirección local de la API, cómo se inicia para pruebas, la configuración CORS o de acceso desde la extensión y un conjunto de casos de prueba sin credenciales privilegiadas. No entregar claves secretas para empaquetarlas en el frontend.

**Necesario antes de:** las pruebas finales en Chrome.

## Seguimiento

Para cada punto, registrar respuesta, fecha y ejemplo de payload cuando esté disponible. Si la API difiere de `FRONTEND_CONTEXT.md`, usar el contrato real confirmado para la implementación y actualizar la documentación de integración cuando el equipo lo acuerde.
