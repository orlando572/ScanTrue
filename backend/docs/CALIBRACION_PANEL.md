# Calibración desde el panel

En **Administración → Calibración** (`/admin/calibracion`) se calibra una pareja BiLSTM + BETO/mBERT. El flujo es Datasets → Entrenamiento → **Calibración** → Modelos: calibrar no entrena ni despliega. Crea una versión calibrada nueva que se despliega desde Modelos.

## Qué es calibrar

- **Temperatura:** cada modelo tiene una temperatura T que convierte su logit en una probabilidad bien calibrada, `p = sigmoide(z / T)` con `z = logit_falsa − logit_real`. Se ajusta con las **predicciones fuera de pliegue** del modelo (minimiza el log-loss), es decir, con textos que no vio al entrenar.
- **Combinación:** `p_falsa = sigmoide(w_bilstm · z_bilstm / T_bilstm + w_mbert · z_mbert / T_mbert)`. Los pesos son una decisión de diseño; el vigente es 0,20/0,80.
- **Validación:** como en `datos_comunes/calibrar_conjunto.py`, por fuente (se ajusta con dos fuentes y se mide en la tercera). Incluye los niveles de la extensión, la regla de discrepancia (evaluada, no aplicada) y la comparación por bootstrap.

**El mismo resultado que hoy:** con la pareja B6 + M3b, peso 0,20 y temperaturas ajustadas sale exactamente la calibración de producción (también con un B6 reentrenado desde el panel **en la GPU**; uno entrenado en CPU da otra T, ver [ENTRENAMIENTO_PANEL.md](ENTRENAMIENTO_PANEL.md)):
- T 8,4468 y 2,1347, y pesos 0,2/0,8;
- el `metricas.json` de `comun_v1_corridas/calibracion/`, idéntico número a número;
- desplegar esos contratos calibrados da en `POST /analisis` las mismas probabilidades, nivel y comparación. Solo cambian los nombres de versión (`version_combinacion` y la versión de cada modelo).

## Qué se puede editar

| Campo | Notas |
| --- | --- |
| Pareja | Cualquier BiLSTM y cualquier BETO/mBERT del catálogo que tenga predicciones fuera de pliegue (ver abajo) |
| Peso del BiLSTM | 0–1, en pasos de 0,05. Si no es el vigente, hay que dar un motivo |
| Temperaturas | *Ajustada* (por defecto) o *A mano* para cada modelo. Con T a mano, la combinación elegida se valida con esas T fijas y el informe guarda las dos: la ajustada y la usada |

La **semilla no se edita**: es un dato del entrenamiento. Se usan las predicciones de la semilla con la que se entrenó cada modelo (`semillas[0]` de su contrato).

**Calcular** muestra el resultado sin guardar nada; tarda unos 10 s. **Guardar calibración** lo vuelve a calcular y guarda la versión.

## Qué modelos se pueden calibrar

Los que tienen predicciones fuera de pliegue con la semilla de su contrato. Se buscan, en este orden:
1. en el campo `predicciones_fuera_de_pliegue` del contrato: los reentrenados con «Preparar para calibrar» y los calibrados desde el panel;
2. junto al contrato de `origen`: B6 y M3b de producción (`datasets/comun_v1_corridas/{bilstm,mbert}/final/`), sin tocar sus contratos, que están en Git;
3. junto al propio contrato.

Las predicciones deben traer sus etiquetas (`id_articulo`, `fuente`, `etiqueta_falsa`, como las que deja `reentrenar --pliegues`) o ser de `comun_v1`, que está en el equipo.

Si los dos modelos no comparten conjunto (por ejemplo, un BiLSTM reentrenado con una versión del panel junto a M3b), cada T se ajusta por su lado y la combinación no se puede validar en conjunto; el panel lo avisa.

## Qué guarda

`datasets/calibraciones/<versión>/` (fuera de Git), con versión `<conjunto>_conjunta_<AAAAMMDD>_<4 hex>`:
- `combinacion.json`: el mismo formato que `datasets/combinacion_produccion/combinacion.json`, más `origen`, `modelos_origen`, `fecha` y `por` y, si hay T a mano, `temperaturas_ajustadas` y `temperaturas_manuales`;
- `metricas.json`, `RESUMEN.md` y `predicciones_combinadas_fuera_de_pliegue.csv`, como la CLI;
- `bilstm/contrato.json` y `mbert/contrato.json`: los **contratos calibrados**. Son el contrato de origen con:
  - versión `<versión de origen>_cal_<AAAAMMDD>_<4 hex>`;
  - la T calibrada y `temperatura_provisional: false`;
  - `calibracion` y `calibrado_desde`;
  - las rutas de los pesos y del tokenizador escritas desde la raíz del repositorio, hacia los **mismos archivos**, sin copiarlos (BETO pesa 440 MB).

  Llevan también las métricas del modelo de origen (el umbral 0,5 no depende de T).

No se modifica ningún contrato existente ni lo desplegado. Se escribe en una carpeta oculta `.parcial` y se renombra al terminar. Desde el panel no se borran calibraciones, porque borraría modelos.

## Cómo llega a los análisis

1. **Desplegar** (en Calibración, junto a cada calibración guardada y al guardarla) pone la pareja calibrada y sus pesos en **un solo cambio**: una entrada en el historial, y «Volver atrás» en Modelos la deshace entera. Modelos también muestra los contratos calibrados como «Disponible», con origen *Calibración*, y se pueden desplegar uno a uno; mientras falte el segundo, `version_combinacion` es `panel: …`.
2. Al desplegar una pareja, la API busca su combinación calibrada (`calibration_for` en `backend/services/model_registry.py`) entre la de producción y las de `datasets/calibraciones/`. Si los contratos, las temperaturas y los pesos coinciden, `version_combinacion` es la de esa calibración. Si no (por ejemplo, otros pesos en el deslizador), es `panel: …`, como antes.
3. «Volver a los calibrados», en Modelos, usa los pesos de la calibración de la pareja desplegada.

## API (todas con sesión de administrador)

| Ruta | Qué hace |
| --- | --- |
| `GET /admin/calibraciones/opciones` | Candidatos por tipo (aptos o con su motivo), pareja y peso por defecto, calibración vigente y la de producción |
| `POST /admin/calibraciones/vista-previa` | `{"bilstm", "mbert", "peso_bilstm", "temperaturas": {"bilstm": null \| T, "mbert": null \| T}}` → resultado sin guardar |
| `POST /admin/calibraciones` | Lo mismo + `motivo` → 201 con la versión guardada |
| `GET /admin/calibraciones` | La de producción, las guardadas y la vigente |
| `GET /admin/calibraciones/{versión}` | Una calibración con su informe |
| `POST /admin/modelos/desplegar-calibracion` | `{"version"}` → despliega la pareja y los pesos de esa calibración (también la de producción) en un solo cambio. 404 `calibracion_no_encontrada`, 409 `ya_desplegado` |

Código: `backend/services/calibration.py`. Motor: `calibrar_predicciones` en `datos_comunes/calibrar_conjunto.py`; la CLI sigue igual y da el mismo resultado. Pruebas: `backend/tests/test_calibration.py`, que incluye la comparación con producción.
