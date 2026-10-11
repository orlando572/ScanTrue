# P12 Registro y confirmación

## Estado de este archivo

Plan individual de P12. La primera fase ya muestra el formulario dentro del popup, sin conectar el registro con el backend. La creación de la cuenta y la confirmación de correo quedan para una fase posterior.

P12 sigue `SISTEMA_DISENO.md` y se abre desde **Crear cuenta** en P11 o P13. No hay un prototipo específico de P12; se usarán los patrones visuales ya acordados para las demás pantallas.

## Objetivo

Permitir que el usuario vea y complete el formulario de registro, entienda sus campos y pueda volver o ir a **Iniciar sesión**. Cuando se integre el backend, el mismo recorrido permitirá crear la cuenta y atender su estado de confirmación sin perder la sesión invitada.

## Primera fase implementada: formulario visible, sin backend

### Contenido y jerarquía

1. Cabecera común, acción **Volver** y título **Crear cuenta**.
2. Campo **Correo electrónico** con etiqueta visible.
3. Campo **Contraseña** con etiqueta visible y control accesible para mostrarla u ocultarla.
4. Campo **Confirmar contraseña** con el mismo control de visibilidad.
5. Errores locales breves junto al campo afectado.
6. Acción **Crear cuenta**, deshabilitada mientras el registro no esté conectado, con una explicación breve: **El registro aún no está disponible**.
7. Acceso secundario **Ya tengo cuenta** que abre P13 dentro del popup.

El formulario se puede recorrer y completar. La validación local comprueba campos obligatorios, formato básico del correo y coincidencia de las contraseñas; sus mensajes sirven para corregir lo escrito, pero no afirman que el correo exista o que la cuenta se haya creado. Si la acción principal está deshabilitada, la explicación permanecerá visible y no dependerá de pasar el cursor sobre el botón.

### Acciones y navegación

| Acción | Resultado en la primera fase |
| --- | --- |
| **Volver** | Regresar a la vista de origen, normalmente P11, sin cambiar la sesión. |
| Mostrar u ocultar contraseña | Cambiar solo la presentación del campo correspondiente. |
| **Crear cuenta** | No envía datos ni simula un registro; permanece deshabilitada con explicación. |
| **Ya tengo cuenta** | Abrir P13 dentro del popup. |

No se muestra un éxito, un correo enviado ni una cuenta pendiente de confirmación por completar el formulario. No se guardan el correo ni las contraseñas en el almacenamiento de la extensión y no se registran en consola. Al salir de P12, se descartan los valores escritos. La sesión y el historial del invitado siguen disponibles.

## Fase posterior: conexión con el backend

Una vez confirmado el contrato de `POST /cuentas` y sus respuestas, se habilitará **Crear cuenta** para enviar una sola solicitud. La sesión invitada se conservará hasta que la API confirme la transición. La respuesta real determinará si la cuenta queda activa o pendiente de confirmación de correo; solo entonces se mostrará el estado correspondiente. Los errores de validación o del servicio permitirán corregir o reintentar sin afirmar que se creó una cuenta.

La integración deberá verificar cómo se incorpora el historial invitado y mostrar una cantidad de registros incorporados únicamente si la API la devuelve. Los detalles pendientes del contrato se mantienen en `DEPENDENCIAS_BACKEND.md`. La pantalla no expondrá tokens ni mecanismos de autenticación.

## Estados previstos

| Estado | Primera fase | Tras la integración |
| --- | --- | --- |
| Formulario inicial | Campos vacíos y registro no disponible. | Campos vacíos y acción habilitable cuando los datos sean válidos. |
| Datos incompletos o inválidos | Corrección local cerca del campo, conservando lo escrito mientras se permanece en P12. | Igual, más errores que devuelva la API. |
| Envío en curso | No aplica. | Indicar **Creando cuenta** y evitar el doble envío. |
| Cuenta pendiente de confirmación | No se muestra. | Explicar que debe revisar su correo solo si la API devuelve ese estado; conservar la sesión invitada. |
| Cuenta activa | No se muestra. | Actualizar la sesión solo tras éxito confirmado y abrir P11. |
| Error del servicio | No aplica. | Conservar el formulario y permitir reintentar. |

## Aplicación del sistema de diseño

- Usar los tokens de color, tipografía, espaciado, campos y botones de `SISTEMA_DISENO.md`.
- Organizar el formulario en una columna dentro del popup; permitir desplazamiento vertical cuando haga falta.
- Mantener etiquetas visibles, orden de foco lógico y controles de contraseña con nombre accesible.
- Mostrar errores bajo el campo y la indisponibilidad del registro junto a la acción.
- Evitar información técnica sobre el backend en los textos de la interfaz.

## Orden de implementación de P12

1. Construir la vista React del formulario y conectarla con la navegación existente desde P11 y P13.
2. Aplicar el sistema de diseño, los controles de visibilidad y la validación local; mantener deshabilitado el registro real con su explicación.
3. Revisar en Chrome el tamaño del popup, el desplazamiento, el teclado, el foco y que no se persistan datos sensibles.
4. En una fase posterior, confirmar el contrato con el backend e integrar registro, confirmación, errores, sesión e incorporación de historial.

## Criterios de aceptación de la primera fase

- **Crear cuenta** en P11 abre el formulario P12 dentro del popup; **Volver** y **Ya tengo cuenta** navegan dentro del popup.
- Se ven y pueden completar los tres campos; los controles de contraseña y los errores locales son accesibles.
- El usuario comprende que el registro aún no está disponible. No se envían solicitudes, no se crea una cuenta aparente y no se muestra una confirmación ficticia.
- Salir del formulario no altera la sesión ni el historial del invitado, y no conserva las contraseñas.
- La vista aplica `SISTEMA_DISENO.md`.

## Pendiente para la fase de integración

Confirmar las respuestas actuales de `/cuentas`, los requisitos de contraseña, la confirmación de correo y la incorporación del historial invitado. Esta fase se planificará contra el contrato real antes de habilitar el envío.
