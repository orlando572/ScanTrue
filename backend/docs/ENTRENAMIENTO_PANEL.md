# Entrenamiento desde el panel

En **Administración → Entrenamiento** (`/admin/entrenamiento`) se reentrena un BiLSTM o un BETO/mBERT con nuestros datos, sin abrir una terminal. El panel **solo entrena**: el modelo nuevo aparece en **Modelos** y se despliega desde allí. Desde Entrenamiento no se despliega, no se borra ni se sobrescribe ningún modelo.

## Qué hace

1. **Receta:** la `config.json` de la corrida que dejó el modelo desplegado de ese tipo (hiperparámetros, brazo de ablación y épocas fijas). Si el desplegado no la trae (por ejemplo, uno importado) o el tipo está retirado, se usa la de producción: B6 (`datasets/bilstm_produccion/modelo/config.json`) o BETO M3b (`datasets/mbert_produccion/modelo/config.json`). En el panel se pueden cambiar las épocas y la semilla.
2. **Datos:** cualquiera de nuestros conjuntos:
   - `datasets/comun_v1`: todo su desarrollo, más los brazos que pida la receta. Su prueba congelada no se abre nunca, así que el modelo sale sin métricas.
   - **Un conjunto combinado de Datasets** ([CONJUNTOS_COMBINADOS.md](CONJUNTOS_COMBINADOS.md)): `comun_v1` sin cambios más las noticias del panel, que solo se suman al entrenamiento (brazo `panel`, además de los de la receta). Se evalúa con la prueba de sus versiones y se calibra con M3b como B6. Usa su propia caché de fastText.
   - **Una versión del panel de Datasets** (creada con el estándar de fragmentos). Su partición de entrenamiento se usa como desarrollo y su partición de prueba sirve para evaluar al terminar (`metricas.json`, por noticia). Los brazos de la receta se omiten porque la versión no los trae, y queda anotado. Se rechazan las versiones anteriores al estándar y las que tienen una sola clase.
3. **Entrena desde cero:** el BiLSTM parte de fastText y BETO/mBERT de su modelo base. Si el modelo base no está en `datasets/modelos_base/`, se descarga primero (~440 MB, una vez). Usa todo el desarrollo (`--pliegue todo`), las épocas de la receta y una semilla.
4. **Guarda una versión nueva** en `datasets/entrenamientos/<tipo>/<versión>/` (fuera de Git), con:
   - `contrato.json`;
   - los pesos (`todo_s<semilla>/`);
   - `entrenamiento.json` (procedencia: conjunto con SHA-256, receta, épocas, brazos omitidos y tiempo);
   - `metricas.json`, si hubo prueba.

   La versión es `<fuente>_<configuración>_<AAAAMMDD>_<4 hex>`, por ejemplo `comun_v1.1_B6_20261116_e151` o `panel-abril_B6_…`.
5. **Pendiente de calibrar:** el contrato sale con `temperatura: 1.0` y `temperatura_provisional: true`. Modelos lo muestra al momento, pero no se puede desplegar hasta calibrarlo en **Calibración** ([CALIBRACION_PANEL.md](CALIBRACION_PANEL.md)).
6. **Preparar para calibrar** (casilla, activa por defecto; `--pliegues`): antes del modelo final entrena F1, F2 y F3 con la misma receta y semilla, con la parada temprana de los experimentos (`epocas_max` y `paciencia` de la receta). Guarda `predicciones_fuera_de_pliegue.csv` con sus etiquetas y lo anota en el contrato. Sin esto, el modelo no se puede calibrar. Tarda unas 4 veces más: con el BiLSTM y comun_v1, ~1 min en GPU. Las versiones del panel se reparten en F1–F3 por grupo y clase, con un sorteo fijo; si son demasiado pequeñas (menos de 3 grupos por clase), la opción se rechaza.

Con `comun_v1`, la receta de B6, la semilla 42 y **la GPU (CUDA)** se obtiene exactamente el mismo `modelo.pt` que el de producción (mismo SHA-256) y, con «Preparar para calibrar», las mismas predicciones fuera de pliegue. Por eso, al calibrarlo con M3b, sale la misma T = 8,4468: la receta es reproducible. **En el procesador (CPU) el modelo sale distinto** (los cálculos en coma flotante no dan los mismos bits), así que su SHA-256 y su temperatura calibrada también cambian. Comprobado el 15 nov 2026: GPU `9392da59…` = producción; CPU `233f64b1…`.

## Cómo corre

- La API lanza `bilstm/entrenar.py reentrenar` o `mBERT/entrenar.py reentrenar` en otro proceso (código en `backend/services/training.py`). BETO/mBERT se ejecuta con `PYTHONPATH=backend/.deps`, porque `transformers` está ahí.
- **Un entrenamiento a la vez.** En el panel se elige **GPU (CUDA)** o **Procesador (CPU)**; por defecto, la GPU si la hay. Pedir la GPU sin CUDA se rechaza (422 `sin_gpu`).
- **El script no deja nada a medias:** escribe en `.<versión>.parcial` (oculta, el catálogo no la ve) y solo la renombra al terminar. Si falla o se cancela, la borra. Nunca escribe sobre una carpeta que ya exista.
- **Progreso:** con `--progreso`, el script imprime líneas JSON (`{"progreso": "entrenando", "epoca", "epocas", "lote", "lotes"}`) que el panel lee del registro. Mientras entrena, el panel consulta cada 2 s y muestra el avance, la fase, cada época con su pérdida y la cola del registro.
- **Estado** en `backend/.local/entrenamientos/<id>/` (fuera de Git): `estado.json`, `registro.log` y, si la fuente es del panel, la copia del conjunto. Se calcula al leer:

  | Estado | Cuándo |
  | --- | --- |
  | Completado | Existe la carpeta del modelo con su contrato |
  | En curso | El proceso sigue vivo (aunque la API se haya reiniciado) |
  | Cancelado | Se canceló desde el panel |
  | Falló | El proceso terminó sin contrato (el panel muestra el error del registro) |
- **Cancelar** envía `SIGTERM` al proceso. Si no termina en 15 s, se fuerza, y después se borra su carpeta parcial.

## A mano

```bash
bilstm/.venv/bin/python bilstm/entrenar.py reentrenar \
  --receta datasets/bilstm_produccion/modelo/config.json \
  --conjunto datasets/comun_v1 \
  --salida datasets/entrenamientos/bilstm/mi_version --version mi_version
```

Opciones: `--epocas`, `--semilla`, `--dispositivo cuda|cpu`, `--pliegues` (preparar para calibrar), `--progreso` y, solo en el BiLSTM, `--cache` (caché de fastText; una por conjunto). En `mBERT/entrenar.py` es igual, con `PYTHONPATH=backend/.deps` en Linux.

## API (todas con sesión de administrador)

| Ruta | Qué hace |
| --- | --- |
| `GET /admin/entrenamientos/opciones` | Receta de cada tipo, fuentes (`comun_v1` y versiones del panel, con si son aptas), si hay CUDA y la carpeta de salida |
| `POST /admin/entrenamientos` | `{"tipo", "fuente": {"tipo": "comun_v1"} \| {"tipo": "panel", "version_id"} \| {"tipo": "conjunto", "version"}, "epocas"?, "semilla"?, "dispositivo"?: "cuda" \| "cpu", "pliegues"?: bool (por defecto `true`, como la casilla del panel)}` → 202. 409 si ya hay uno en curso |
| `GET /admin/entrenamientos` | Entrenamiento activo e historial |
| `GET /admin/entrenamientos/{id}` | Detalle con las últimas líneas del registro |
| `POST /admin/entrenamientos/{id}/cancelar` | Cancela uno en curso |

Pruebas: `backend/tests/test_training.py` (sin entrenar), `bilstm/tests/test_entrenar.py` (`ReentrenarTests`, en CPU con un conjunto sintético) y `mBERT/tests/test_entrenar.py` (receta y opciones, sin entrenar).
