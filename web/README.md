# ScanTrue web

Plataforma web de ScanTrue (incrementos 1 y 3 de [`docs/INCREMENTOS.md`](../docs/INCREMENTOS.md)). Es una aplicación React + Vite + Tailwind CSS, separada de la extensión (`frontend/`), que habla con la misma API (`backend/`).

| Página | Ruta | Quién | Qué muestra |
| --- | --- | --- | --- |
| Inicio | `/` | Cualquiera | Qué es ScanTrue, los tres criterios, estado de los servicios y totales. |
| Resultados | `/resultados` | Cualquiera | Todos los análisis: fragmentos, salida de cada modelo, buscador y filtros. |
| Detalle | `/resultados/:id` | Cualquiera | Dial, fragmentos completos, qué leyó cada modelo y registro en blockchain. |
| Administración | `/admin` | Solo administradores | Panel, casos y revisión, versiones de dataset y versiones de modelos. |

Los visitantes no inician sesión: los resultados son públicos y nunca muestran quién hizo cada análisis. La única sesión es la del administrador y vive en `sessionStorage` (se pierde al cerrar la pestaña).

## Arrancar

Se necesita Node.js 20.19 o superior y la API encendida (ver [`backend/README.md`](../backend/README.md)).

```bash
cd web
npm install
npm run dev        # http://127.0.0.1:5174
```

- La API se busca en `http://127.0.0.1:8000`. Para otra dirección, crea `web/.env.local` con `VITE_API_BASE=https://…`.
- La API solo acepta a la web desde los orígenes de `WEB_ORIGINS` (`backend/.env`); por defecto, `http://127.0.0.1:5174` y `http://localhost:5174`.
- `npm run build` genera `dist/`. Es una aplicación de una sola página: el servidor que la publique debe devolver `index.html` para cualquier ruta.
- `npm test` ejecuta las pruebas de filtros y presentación (`node --test`).

## Cuenta de administrador

El rol vive en `app_metadata.role = "admin"` de Supabase Auth y solo se cambia con la clave secreta. Desde la raíz del repositorio:

```bash
PYTHONPATH=backend/.deps:. bilstm/.venv/bin/python -m backend.crear_admin correo@ejemplo.com
```

Si la cuenta no existe, la crea y pide la contraseña por teclado; si existe, la asciende. Con `--quitar` retira el rol.

## Qué hace el administrador

- **Panel:** totales, reparto por nivel, acuerdo entre modelos, revisiones, análisis por día y versión de modelos activa.
- **Casos y revisión:** lista con filtros; por defecto van primero los casos donde BiLSTM y BETO no coinciden. En cada caso se elige la etiqueta correcta (**Falsa** o **Real**: si coincide con el modelo queda *aprobado*; si no, *corregido*) o se **descarta**, con nota, enlaces de evidencia y grupo de evento. Atajos: `A` aprueba, `F` falsa, `R` real, `D` descarta, `J`/`K` siguiente y anterior. También se puede ocultar un caso de la web pública.
- **Datasets:** crea una versión con los casos aprobados o corregidos. Retira copias exactas y textos con etiquetas contrarias, agrupa los casos de la misma página o del mismo evento y manda cada grupo entero a entrenamiento o a prueba. Se descarga en CSV, con un manifiesto JSON.
- **Modelos:** lista las versiones de `backend/despliegues/`, con sus métricas y una comparación lado a lado. **Activar** carga y comprueba la versión antes de sustituir a la actual; **Volver a la anterior** deshace el último cambio.

## Tercer criterio (incremento 2)

La verificación web todavía no existe, pero la web ya tiene su sitio: la tarjeta de cada resultado, el panel «Verificación web» del detalle y el filtro de Resultados. Cuando el backend rellene la tabla `verificaciones_web`, la API devolverá `verificacion_web` y la web lo mostrará sin cambios (`presentVerification` en `src/lib/presentation.js`).

## Estructura

```text
web/
├── docs/SISTEMA_DISENO_WEB.md
├── src/
│   ├── components/   VectorField (fondo), Shell, Analysis, Filters, ui
│   ├── lib/          api, filters, presentation, hooks
│   ├── pages/        Home, Results, ResultDetail y admin/
│   ├── App.jsx, main.jsx, styles.css
└── tests/            filters.test.js, presentation.test.js
```

La lógica de niveles, desglose por modelo, fechas, métricas y estado de servicios se importa de `../frontend/src/popup/*-presentation.js`, para que un mismo resultado se lea igual en la extensión y en la web.
