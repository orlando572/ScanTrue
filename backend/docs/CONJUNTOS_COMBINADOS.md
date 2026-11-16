# Conjuntos combinados (Datasets del panel)

En **Administración → Datasets**, debajo de las versiones, se crea un **conjunto combinado**: `comun_v1` más las noticias revisadas de una o varias versiones del panel, sin repetir ninguna. Se elige como fuente en **Entrenamiento** ([ENTRENAMIENTO_PANEL.md](ENTRENAMIENTO_PANEL.md)).

## comun_v1 no cambia

- `fragmentos_desarrollo.csv` y los `ablacion_*.csv` se copian **byte a byte** (mismo SHA-256 y mismos pliegues F1–F3). La prueba congelada no se copia.
- Las noticias del panel van aparte, en `extra_panel.csv` (pliegue `panel`). Los scripts las suman al entrenamiento como un brazo más (`BRAZOS["panel"]` en `datos_comunes/comun.py`): entran en el entrenamiento de F1, F2, F3 y del modelo final, pero **nunca** en la validación.
- Por eso la validación por fuente, las predicciones fuera de pliegue y la calibración siguen siendo las de `comun_v1`. El contrato del modelo lleva el `sha256_conjunto` de `comun_v1`, así que se calibra con M3b igual que B6.
- La prueba de las versiones va en `fragmentos_prueba.csv` y evalúa el modelo al terminar (`metricas.json`).

Sin `comun_v1` (casilla desmarcada), el conjunto es la unión de las versiones con el formato de una versión del panel: `fragmentos_desarrollo.csv` repartido en F1–F3 por grupo y clase.

## Cómo se junta

1. **Sin repetir:** por `id_fragmento`, manda la versión más reciente (por si se corrigió la etiqueta).
2. **Prueba primero:** una noticia o un grupo que esté en la prueba de alguna versión va a prueba, aunque en otra versión estuviera en entrenamiento.
3. **Cruce con comun_v1:** el mismo texto que una fila de `comun_v1` se retira (ya está). Un casi duplicado de una fila del desarrollo toma su grupo, así nunca se entrena con él en el pliegue donde valida su gemela. Lo que cruce con la prueba congelada se retira.
4. **Balanceo** (opcional): ver abajo.

## Balanceo: ¿hace falta 50/50?

- Al entrenar, las reales y las falsas **ya pesan lo mismo** en total (`pesos_de_clase` en `bilstm/entrenar.py` y `mBERT/entrenar.py`). `comun_v1` tiene 1011 noticias reales y 557 falsas (64/36) y entrena como si fuera 50/50, sin tirar datos.
- Que tenga más reales no lo hace mejor ni peor: refleja sus fuentes, y en la realidad circulan más noticias reales que falsas.
- **«Equilibrar lo añadido 50/50»** retira noticias enteras (grupos completos, en un orden fijo que sale de la clave del grupo) de la clase que sobra **entre las del panel**, después de juntar y quitar duplicados. Nunca toca `comun_v1` ni la prueba, y nunca duplica noticias. Úsalo si lo revisado está muy cargado hacia una clase.

## Qué guarda

`datasets/conjuntos/<versión>/` (fuera de Git), con versión `<nombre>_<AAAAMMDD>_<4 hex>`: los archivos de arriba y `manifest.json` (fuentes con su SHA-256, balanceo pedido, conteos antes y después, y el SHA-256 de cada archivo). Se escribe en una carpeta oculta `.parcial` y se renombra al terminar. Borrar un conjunto no afecta a los modelos ya entrenados con él.

## API (con sesión de administrador)

| Ruta | Qué hace |
| --- | --- |
| `GET /admin/conjuntos` | Lista de conjuntos |
| `POST /admin/conjuntos/vista-previa` | `{"versiones": [uuid], "incluir_comun"?: true, "balanceo"?: "ninguno" \| "50_50"}` → conteos, sin guardar |
| `POST /admin/conjuntos` | Lo mismo + `nombre` y `descripcion?` → 201. 409 `nombre_repetido` o `version_anterior_al_estandar`; 422 `una_sola_clase_para_equilibrar` |
| `GET /admin/conjuntos/{versión}` | Un conjunto con su manifiesto |
| `DELETE /admin/conjuntos/{versión}` | Lo borra |

Código: `backend/services/combined_sets.py`. Pruebas: `backend/tests/test_combined_sets.py` y `ReentrenarTests.test_combinado_suma_el_panel_solo_al_entrenamiento` en `bilstm/tests/test_entrenar.py`.
