# Cambio de modelos: B6 y BETO calibrados (11 nov 2026)

Este cambio sustituye los modelos de octubre por los entrenados con el conjunto común y aplica la calibración conjunta. Decisiones y cifras: [docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md](../../docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md).

## Qué cambia para quien usa la API

| | Antes | Ahora |
| --- | --- | --- |
| Modelo `bilstm` | `pequeno_mejorado_fasttext_cc300_s42` | B6, versión `comun_v1.1_B6_20261107` |
| Modelo `mbert` | mBERT multilingüe, `mBERT_BiLSTM_main_len512_seed43` | **BETO** M3b, versión `comun_v1.1_M3b_20261111`. La clave sigue siendo `mbert` |
| `probabilidad_falsa` de cada modelo | Softmax sin calibrar | Calibrada con la temperatura del contrato (BiLSTM 8,4468, BETO 2,1347) |
| Resultado unificado | Media de probabilidades, 70 % mBERT y 30 % BiLSTM | `sigmoide(0,2 · logit(p_bilstm) + 0,8 · logit(p_beto))` |
| Configuración de pesos | `ANALYSIS_MBERT_WEIGHT` | `datasets/combinacion_produccion/combinacion.json` (la variable se ignora) |
| Lectura máxima | mBERT 512 subpalabras; el BiLSTM, 192 dentro de ese recorte | BETO 256 subpalabras y BiLSTM 192 palabras, cada uno sobre el prefijo más largo de los dos |
| `resultado_unificado` | `version_regla` | `version_regla` (sigue siendo `media_ponderada_v1`, lo exige la base de datos) y `version_combinacion` nuevo |
| `GET /metricas` | Validación y pruebas de octubre | Validación por fuente no vista (global y por fuente) de B6 y BETO |

El resto del contrato (`POST /analisis`, historial, verificación, mínimo de 100 tokens, `texto_recortado`) no cambia. No hace falta ninguna migración de Supabase: `version_combinacion` es un campo más dentro del JSON `resultado_unificado`.

## Archivos

| Archivo | Papel |
| --- | --- |
| `backend/models/contrato.py` | `ModelContract` (lee y valida un `contrato.json`, verifica SHA-256), `Combination` (lee `combinacion.json`, comprueba que coincide con los contratos y combina) |
| `backend/models/bilstm.py` | Carga B6 según su contrato; `predict_logits()` devuelve `logit_falsa − logit_real` |
| `backend/models/mbert.py` | Carga BETO y su tokenizador según su contrato |
| `backend/services/analysis.py` | Recorte por modelo y combinación calibrada |
| `backend/core/config.py`, `backend/app.py` | Cargan la combinación al arrancar y la comprueban con los contratos |
| `backend/tests/test_analysis_combination.py` | Pruebas de la combinación, los contratos de producción y el recorte, sin cargar pesos |
| `backend/metrics/*.json` | Generados con `datos_comunes/publicar_metricas.py`; los de octubre, en `backend/metrics/archivo_octubre/` |

## Qué hace el backend al arrancar

1. Lee `datasets/combinacion_produccion/combinacion.json` (método `media_ponderada_logits_calibrados`, pesos ≥ 0 que suman 1, sin regla de discrepancia).
2. Lee `datasets/bilstm_produccion/modelo/contrato.json`: etiquetas `real = 0`, `falsa = 1`, temperatura no provisional, una sola semilla. Verifica el SHA-256 de `modelo.pt` y que el checkpoint tenga las mismas etiquetas, longitud y pooling.
3. Lee `datasets/mbert_produccion/modelo/contrato.json` y hace lo mismo con `best_model/model.safetensors` y `tokenizer.json`. Si falla, BETO queda `no_disponible` y el BiLSTM sigue funcionando.
4. Comprueba que la versión y la temperatura de cada contrato coinciden con las de la combinación. Si se cambia un modelo sin recalibrar, el análisis no arranca.

## Cómo se comprobó

- `backend/tests/` (25 pruebas), `datos_comunes/tests/`, `bilstm/tests/`, `mBERT/tests/` y las pruebas del frontend.
- Arranque de la API con `TestClient`: `GET /salud` marca los dos modelos disponibles.
- El backend reproduce los logits del entrenamiento (BiLSTM exacto; BETO con diferencias de hasta 0,024 por BF16 en GPU).
