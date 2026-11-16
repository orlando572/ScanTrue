# ScanTrue web

Plataforma web de ScanTrue (incrementos 1 y 3 de [`docs/INCREMENTOS.md`](../docs/INCREMENTOS.md)). Es una aplicación React + Vite + Tailwind CSS, separada de la extensión (`frontend/`), que habla con la misma API (`backend/`).

| Página | Ruta | Quién | Qué muestra |
| --- | --- | --- | --- |
| Inicio | `/` | Cualquiera | Qué es ScanTrue, los tres criterios, estado de los servicios y totales. |
| Resultados | `/resultados` | Cualquiera | Todos los análisis: fragmentos, salida de cada modelo, buscador y filtros. |
| Detalle | `/resultados/:id` | Cualquiera | Dial, fragmentos completos, qué leyó cada modelo y registro en blockchain. |
| Administración | `/admin` | Solo administradores | Panel, casos y revisión, versiones de dataset, entrenamiento, calibración y versiones de modelos. |

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
- **Datasets:** crea una versión con los casos aprobados o corregidos, con el mismo estándar que el conjunto común `datasets/comun_v1` (`datos_comunes/estandar.py`):
  - Limpia cada noticia como comun_v1, deja fuera las que no están en español y la corta a 400 palabras como máximo.
  - La parte en fragmentos de 100 a 200 palabras hechos de oraciones completas (terminan en `.`, `!`, `?` o `…`), cada uno con peso 1/n.
  - Retira copias exactas y textos con etiquetas contrarias, y retira también las noticias que ya están en la prueba congelada de comun_v1. Las que están en su desarrollo van siempre a entrenamiento.
  - Agrupa los casos de la misma página, del mismo evento o casi iguales, y manda cada grupo entero a entrenamiento o a prueba. La prueba se toma por clase (≈20 % de las falsas y de las reales).
  - Se descarga como CSV con toda la procedencia o como **ZIP para entrenar**: `fragmentos_entrenamiento.csv` y `fragmentos_prueba.csv` con las columnas de comun_v1, `procedencia.csv` y `manifest.json` con el SHA-256 de cada archivo. `datos_comunes/comun.py:leer()` carga esos CSV directamente.
- **Entrenamiento:** reentrena un BiLSTM o un BETO/mBERT desde cero con la receta del modelo desplegado y `comun_v1` o una versión de Datasets. Se elige GPU o procesador y si se prepara para calibrar (entrena también los 3 pliegues). Muestra el avance en vivo: anillo de progreso, fases, cada corrida y época con su pérdida, y el registro. Se puede cancelar. El modelo nuevo aparece en Modelos como «Pendiente de calibrar»; desde aquí no se despliega ni se borra nada. Ver [backend/docs/ENTRENAMIENTO_PANEL.md](../backend/docs/ENTRENAMIENTO_PANEL.md).
- **Calibración:** calibra una pareja BiLSTM + BETO/mBERT con sus predicciones fuera de pliegue. Se editan la pareja, el peso y las temperaturas (ajustadas o a mano). Muestra la validación por fuente, los niveles de la extensión y si coincide con la calibración de producción. Guardar crea contratos calibrados nuevos que se despliegan en Modelos. Ver [backend/docs/CALIBRACION_PANEL.md](../backend/docs/CALIBRACION_PANEL.md).
- **Modelos:** un modelo desplegado por tipo (BiLSTM y BETO/mBERT). Lista los del repositorio, los que deja el entrenamiento (aparecen solos; «Pendiente de calibrar» hasta la calibración conjunta) y los importados en ZIP, con sus métricas y una comparación dentro de cada tipo. **Desplegar** carga y comprueba el modelo antes de sustituir al de su tipo; **Retirar** deja el análisis con el otro (debe quedar uno). Los pesos se editan con un deslizador (por defecto los calibrados, 20/80). **Volver atrás** deshace el último cambio. Ver [backend/docs/DESPLIEGUE_MODELOS.md](../backend/docs/DESPLIEGUE_MODELOS.md).

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
