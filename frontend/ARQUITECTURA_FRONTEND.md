# Pantallas y arquitectura propuesta del frontend

## Alcance

ScanTrue será una extensión Manifest V3 para Chrome/Chromium. **Todas las pantallas son vistas internas del popup**. React y Tailwind CSS construyen la interfaz; JavaScript nativo se encarga de la selección en la página y del service worker; la extensión se comunica con la API REST de FastAPI. La base del paso 3 ya está creada; las pantallas y sus funciones siguen pendientes de implementación individual.

## Pantallas que quedaron

| Orden | ID | Pantalla | Función | Plan individual |
| --- | --- | --- | --- | --- |
| 1 | P01 | Inicio | Escoger texto y acceder a historial, métricas o cuenta. | `PANTALLA_P01_INICIO_PLAN.md` |
| 2 | P02 | Texto seleccionado | Revisar la selección, analizarla o elegir otra. | `PANTALLA_P02_SELECCION_PLAN.md` |
| 3 | P04 | Análisis en curso | Esperar una única solicitud iniciada desde P02. | `PANTALLA_P04_ANALISIS_PLAN.md` |
| 4 | P05 | Resultado | Ver la salida unificada y abrir el desglose. | `PANTALLA_P05_RESULTADO_PLAN.md` |
| 5 | P06 | Desglose por modelo | Ver las salidas individuales de BiLSTM y mBERT. | `PANTALLA_P06_DESGLOSE_PLAN.md` |
| 6 | P07 | Historial | Recorrer análisis guardados y abrir uno. | `PANTALLA_P07_HISTORIAL_PLAN.md` |
| 7 | P08 | Detalle del historial | Leer el texto y resultado guardados; eliminar con confirmación. | `PANTALLA_P08_DETALLE_HISTORIAL_PLAN.md` |
| 8 | P09 | Métricas de evaluación | Consultar evaluaciones publicadas por la API. | `PANTALLA_P09_METRICAS_PLAN.md` |
| 9 | P11 | Cuenta | Ver el estado de invitado o cuenta y acceder a las acciones de sesión. | `PANTALLA_P11_CUENTA_PLAN.md` |
| 10 | P12 | Registro y confirmación | Mostrar el formulario; crear la cuenta y orientar la confirmación tras la integración futura. | `PANTALLA_P12_REGISTRO_CONFIRMACION_PLAN.md` |
| 11 | P13 | Inicio de sesión | Entrar y tratar la incorporación del historial invitado. | `PANTALLA_P13_INICIO_SESION_PLAN.md` |

P03 se eliminó porque **Analizar** en P02 abre directamente P04. P10 se eliminó por decisión del usuario: la trazabilidad blockchain no se mostrará en el popup. Se mantienen los identificadores restantes para conservar las referencias entre planes.

## Recorridos principales

```text
P01 Inicio ── Escoger texto ──► selección en la página ──► P02
P02 ── Analizar ──► P04 ── respuesta ──► P05 ── desglose ──► P06
P01/P05 ── Historial ──► P07 ── elegir análisis ──► P08 ── desglose ──► P06
P01 ── Métricas ──► P09
Cabecera ── Cuenta ──► P11 ── registro ──► P12
                         └── iniciar sesión ──► P13
```

La navegación **Volver** regresa a la vista de origen. En P06, vuelve a P05 cuando se abrió desde un resultado nuevo y a P08 cuando se abrió desde el historial. Cerrar el popup no equivale a cerrar sesión.

## Estructura de carpetas y módulos previstos

```text
frontend/
├─ ARQUITECTURA_FRONTEND.md       # Este documento
├─ PLAN_FRONTEND.md               # Plan general; planes de pantalla en archivos separados
├─ SISTEMA_DISENO.md
├─ DEPENDENCIAS_BACKEND.md
├─ referencias/                   # Conceptos visuales ya aprobados
├─ popup.html                     # Entrada HTML del popup
├─ package.json
├─ vite.config.js                 # Compilación separada de popup y scripts MV3
├─ public/
│  ├─ manifest.json               # Manifest V3
│  └─ icons/                      # Previsto cuando se definan iconos de la extensión
├─ src/
│  ├─ popup/
│  │  ├─ main.jsx                  # Montaje de React
│  │  ├─ App.jsx                   # Estado y navegación interna
│  │  ├─ screens/                  # Previsto: P01, P02, P04…P09 y P11…P13
│  │  ├─ components/               # Previsto: piezas compartidas de las pantallas
│  │  └─ styles.css                # Entrada de Tailwind y tokens visuales
│  ├─ extension/
│  │  ├─ content-script.js         # Selección de texto en la página
│  │  └─ service-worker.js         # Mensajes, sesión y llamadas a la API
│  └─ shared/                       # Previsto al integrar funciones reales
│     ├─ api/                      # Contratos y adaptación de respuestas FastAPI
│     ├─ messaging/                # Mensajes popup ↔ worker ↔ content script
│     ├─ storage/                  # Selección temporal y sesión persistente
│     └─ format/                   # Fechas y porcentajes para presentación
└─ dist/                           # Salida generada de la extensión; no se edita
```

Los nombres de archivos internos pueden ajustarse al completar el proyecto. Las carpetas marcadas como previstas aún no existen. La separación por responsabilidades debe permanecer: las pantallas presentan datos; los scripts de extensión interactúan con el navegador; los módulos compartidos concentran contratos, almacenamiento y formato. `dist/` es un resultado de compilación, no una fuente.

## Responsabilidades y comunicación

| Parte | Responsabilidad |
| --- | --- |
| Popup React | Mostrar las pantallas, gestionar la navegación interna y enviar acciones del usuario. |
| Content script nativo | Permitir la selección explícita en la página activa y devolver exactamente el texto elegido y su URL. No recibe credenciales. |
| Service worker MV3 | Coordinar mensajes, conservar la selección pendiente, gestionar la sesión y centralizar las solicitudes a FastAPI. |
| Almacenamiento de extensión | Mantener la selección durante la sesión del navegador y la sesión de usuario entre reinicios, conforme al contrato de seguridad confirmado. |
| API REST FastAPI | Validar texto, autenticar, analizar, guardar y entregar historial y métricas. Está fuera de `frontend/`. |

El flujo de captura será: **popup → service worker → content script → service worker → almacenamiento temporal → P02 al reabrir el popup**. El popup puede cerrarse mientras el usuario selecciona en la página; el texto pendiente debe sobrevivir al reinicio del service worker. Al pulsar **Analizar** en P02, el popup solicita al worker una sola operación REST y abre P04. El worker devuelve la respuesta para P05/P06. El historial, el detalle, las métricas y la sesión siguen el mismo punto de comunicación con la API.

Los permisos concretos del manifiesto se fijarán durante la implementación según el flujo de selección y la dirección confirmada de la API. No se añadirá una página de extensión adicional ni una pantalla de blockchain.

## Orden de implementación cuando se autorice

1. Crear la base MV3, la compilación de React/Tailwind y la navegación del popup.
2. Implementar P01 y P02, junto con captura nativa y conservación de la selección.
3. Integrar sesión invitada y API; implementar P04, P05 y P06.
4. Implementar P07 y P08 con historial y eliminación confirmada.
5. Implementar P09 con las métricas disponibles.
6. Implementar P11, después el formulario de P12 sin conexión de registro y, por último, P13 según su plan. Integrar el registro de P12 con la API en una fase posterior.
7. Revisar errores, accesibilidad y recorridos completos en Chrome.

Antes de implementar cada pantalla se revisará su plan individual y su referencia visual. P12 ya tiene un plan para mostrar inicialmente solo el formulario. La creación de cuenta y su confirmación requieren la integración posterior con el backend.
