# Despliegue de modelos desde el panel

En el panel, **Administración → Modelos** (`/admin/modelos`), se elige qué modelo de cada tipo usan los análisis nuevos, sin reiniciar la API y sin tocar archivos a mano. El panel no entrena ni modifica nada del entrenamiento: solo lee lo que este deja.

## Tipos y reglas

| Tipo | Clave | Qué admite |
| --- | --- | --- |
| BiLSTM | `bilstm` | El BiLSTM de `bilstm/modelo.py` |
| BETO / mBERT | `mbert` | BETO (`dccuchile/bert-base-spanish-wwm-cased`) o mBERT (`google-bert/bert-base-multilingual-cased`), con la revisión fijada en `mBERT/modelo.py`. Cualquier otro transformer sale como «No admitido» |

- **Un modelo por tipo:** cada tipo tiene como mucho un modelo desplegado. BETO y mBERT comparten tipo, así que nunca están desplegados a la vez.
- **Retirar:** se puede retirar cualquiera de los dos, pero debe quedar al menos uno. Con uno solo, el resultado unificado es su probabilidad (`comparacion: "no_disponible"`, «Respondió un solo modelo»).
- **Pesos:** se editan en el panel y valen por defecto 20 % BiLSTM y 80 % BETO, los de `datasets/combinacion_produccion/combinacion.json`. La temperatura de cada modelo sale de su propio contrato.
- **Mismo resultado que antes del panel:** mientras estén desplegados B6 y BETO M3b con 20/80, se usa la combinación calibrada tal cual (`version_combinacion = comun_v1.1_conjunta_20261111`), y la respuesta de `POST /analisis` es idéntica. Con otros modelos o pesos, `version_combinacion` pasa a ser `panel: <bilstm> + <beto> @ <pesos>`, salvo que la pareja tenga una calibración guardada en Calibración con esos mismos pesos: entonces es la versión de esa calibración. La forma de la respuesta no cambia y la extensión no necesita cambios.

## De dónde salen los modelos

1. **Manifiestos del repositorio** (`backend/modelos/<tipo>/<versión>.json`): B6 y BETO M3b, marcados como predeterminados, y los de octubre, archivados (sin contrato, solo para comparar métricas).
2. **Detección automática del entrenamiento:** la API busca cada `contrato.json` bajo `datasets/` (se puede cambiar con `MODELOS_BUSCAR_EN`). Incluye los que deja **Administración → Entrenamiento** en `datasets/entrenamientos/<tipo>/<versión>/` ([ENTRENAMIENTO_PANEL.md](ENTRENAMIENTO_PANEL.md)).
   - No entra en `embeddings`, `fuentes`, `unificado`, `comun_v1`, `modelos_base`, `archivo_octubre` ni en carpetas `respaldo*` u ocultas.
   - Un entrenamiento nuevo (`bilstm/entrenar.py` o `mBERT/entrenar.py` con cualquier `--salida` bajo `datasets/`) aparece solo. Mientras está abierto, el panel vuelve a leer el catálogo cada 30 s.
   - Recién entrenado sale **Pendiente de calibrar**, porque su contrato trae `temperatura_provisional: true`. Se calibra en **Administración → Calibración** ([CALIBRACION_PANEL.md](CALIBRACION_PANEL.md)), que crea contratos calibrados nuevos (origen *Calibración*, en `datasets/calibraciones/`) listos para desplegar. La CLI `datos_comunes/calibrar_conjunto.py --actualizar-contratos` sigue sirviendo para los modelos finales de `comun_v1_corridas`.
3. **ZIP importado** desde el panel, para modelos de otro equipo. Debe llevar un único `contrato.json` (en la raíz o en una carpeta), sus pesos y, opcionalmente, `metricas.json`. Se guarda en `datasets/modelos/<tipo>/<versión>/`, fuera de Git. Solo estos modelos se pueden borrar desde el panel.

Las rutas de un contrato se buscan primero junto a él, probando la ruta completa y sus sufijos (`datasets/…/final/todo_s42/modelo.pt` → `todo_s42/modelo.pt` → `modelo.pt`), y después desde la raíz del repositorio. Así sirve el contrato tal como lo deja el entrenamiento, aunque la carpeta se mueva o venga en un ZIP. El SHA-256 del contrato confirma que el archivo es el correcto.

## Qué debe traer un modelo

- **`contrato.json`** con: `modelo` (`bilstm` / `mbert`), `version`, `etiquetas` `{"real": 0, "falsa": 1}`, `max_tokens`, `temperatura` y `temperatura_provisional: false`, `umbral_falsa`, una sola semilla en `semillas` con su checkpoint en `checkpoints.s<semilla>` (`ruta` y `sha256`). Para BETO/mBERT, además: `modelo_base` (`clave`, `hub_id`, `revision`), `entrada: "texto_unico"` y `tokenizador` (`ruta`, `sha256_tokenizer_json`).
- **Pesos:**
  - BiLSTM: el `.pt` del checkpoint.
  - BETO/mBERT: la carpeta del checkpoint, con `model.safetensors`, `config.json` y `tokenizer.json`.
- **`metricas.json`** (opcional): el formato de `GET /metricas` (`backend/schemas/metrics.py`). Sin él, el panel muestra «Sin métricas publicadas».

Si dos modelos tienen la misma `version` y pesos distintos, los dos aparecen; el segundo con `id` `<versión>-<8 primeros caracteres del SHA>`.

## Estados de un modelo

| Estado | Significado |
| --- | --- |
| Disponible | Contrato válido, archivos presentes y SHA-256 correcto. Se puede desplegar |
| Pendiente de calibrar | Temperatura provisional: falta calibrarlo (Administración → Calibración) |
| No admitido | Transformer que no es BETO ni mBERT |
| No válido | Contrato mal formado, faltan archivos o el SHA-256 no coincide (el motivo lo dice) |
| Archivado | Sin contrato de inferencia: solo para comparar métricas |

## Desplegar, retirar y volver atrás

- **Cada cambio** (desplegar, retirar, pesos) carga lo necesario, hace una predicción de prueba y solo si responde bien sustituye al servicio actual. Si algo falla, sigue lo que había.
- **Modelos en memoria:** cambiar el BiLSTM no recarga BETO, y al revés. Los modelos que dejan de usarse se liberan.
- **«Volver atrás»** restaura los modelos y los pesos de antes del último cambio. Un modelo importado que esté desplegado, o que sea al que se volvería, no se puede borrar.
- **Dónde se guarda:** lo desplegado, los pesos y el historial (50 cambios) están en `backend/.local/modelos_desplegados.json`, fuera de Git. Al arrancar se carga lo guardado; si falta o está dañado, los predeterminados. Si un modelo guardado no carga, la API arranca con el otro y el panel lo marca «No cargó».
- **`/salud`** indica en `modelos` qué tipos están cargados y en `desplegados` qué modelo hay en cada uno. **`GET /metricas?modelo=…`** sirve las métricas del modelo desplegado de ese tipo.

## API (todas con sesión de administrador)

| Ruta | Qué hace |
| --- | --- |
| `GET /admin/modelos` | Catálogo por tipo, lo desplegado y cargado, pesos (actuales y calibrados), combinación activa, estado anterior e historial |
| `POST /admin/modelos/desplegar` | `{"tipo", "id"}` |
| `POST /admin/modelos/retirar` | `{"tipo"}` |
| `PUT /admin/modelos/pesos` | `{"bilstm", "mbert"}`, ≥ 0 y sumando 1 |
| `POST /admin/modelos/revertir` | Vuelve al estado anterior al último cambio |
| `POST /admin/modelos/importar` | ZIP como cuerpo crudo (`Content-Type: application/zip`, hasta 2 GB y 4 GB descomprimido) |
| `DELETE /admin/modelos/{tipo}/{id}` | Borra un modelo importado que no esté en uso |

Código: `backend/services/model_registry.py`. Contratos y combinación: `backend/models/contrato.py`. Pruebas: `backend/tests/test_model_registry.py`. Origen de los contratos y la calibración: [CAMBIO_MODELOS_CALIBRADOS.md](CAMBIO_MODELOS_CALIBRADOS.md).
