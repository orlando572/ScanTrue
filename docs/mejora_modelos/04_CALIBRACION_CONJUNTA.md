# Calibración conjunta del BiLSTM y mBERT

**Fecha:** 11 de noviembre de 2026 · **Versión:** `comun_v1.1_conjunta_20261111`
**Plan:** [01_PLAN_COMUN.md §5](01_PLAN_COMUN.md#5-calibración-umbral-y-combinación) · **Script:** [`datos_comunes/calibrar_conjunto.py`](../../datos_comunes/calibrar_conjunto.py)
**Resultados completos (fuera de Git):** `datasets/comun_v1_corridas/calibracion/` (`RESUMEN.md`, `metricas.json`, `combinacion.json` y las probabilidades por fragmento)

## 1. Resumen

| Qué | Decisión |
| --- | --- |
| Modelos | BiLSTM **B6** (semilla 42) y **BETO M3b** (`dccuchile/bert-base-spanish-wwm-cased` + brazo `usmsc`, semilla 42), el ganador de mBERT |
| Temperatura | BiLSTM **T = 8,4468**, BETO **T = 2,1347**. Ya están en el `contrato.json` de cada modelo (`temperatura_provisional = false`) |
| Combinación | **80 % BETO + 20 % BiLSTM** sobre los logits calibrados. Sustituye la media 70/30 de probabilidades sin calibrar de `backend/core/config.py` |
| Umbral | 0,5 sobre la probabilidad combinada |
| Semillas de BETO | Una sola (42): promediar las tres no mejora el F1 (−0,0006, hacía falta +0,01) |
| Regla de discrepancia (§5.2) | Evaluada; **no se aplica** por ahora (ver sección 5) |
| Niveles de la extensión | Los cinco quedan dentro de su objetivo. Con el 70/30 anterior, «Muy probablemente falso» acertaba solo el 75 % |

Fórmula que usará el backend, con `z = logit_falsa − logit_real` de cada modelo:

```
p_falsa = sigmoide(0,20 · z_bilstm / 8,4468 + 0,80 · z_beto / 2,1347)
```

## 2. Qué es y por qué se hace

- **Calibrar** es conseguir que el porcentaje que ve el usuario signifique lo que dice: de los textos marcados con 80 % de «falsa», unos 80 de cada 100 deben ser falsos. Un modelo puede ordenar bien los textos y aun así exagerar su seguridad.
- **Escalado de temperatura:** se divide el logit de cada modelo entre un número `T`, elegido para minimizar el log-loss. No cambia qué texto parece más falso que otro, solo cuánta seguridad muestra. `T` > 1 significa que el modelo exageraba: el BiLSTM mucho (8,45), BETO algo (2,13).
- **Por qué con predicciones fuera de pliegue:** cada fragmento lo predice un modelo que no vio su fuente al entrenar. Ajustar `T` con datos ya vistos daría un modelo «seguro de sí» que fallaría con textos nuevos.
- **Por qué cambian los pesos 70/30:** se fijaron a mano con el mBERT de octubre y mezclan probabilidades sin calibrar. Si un modelo exagera, la mezcla también exagera: con el 70/30, el nivel «Muy probablemente falso» acierta el 75 %, por debajo de su objetivo de 80 %.

## 3. Cómo se eligió la combinación

El plan común proponía una regresión logística que aprendiera los pesos. Se probó, y el resultado fue:

- **Regresión libre:** coeficiente del BiLSTM **negativo** (−0,23 con todos los datos; entre −0,21 y +0,04 por fuente) y ~1 para BETO. Un peso negativo significa que, cuando el BiLSTM dice «falsa», la combinación baja la probabilidad. No es defendible como diseño.
- **Regresión con pesos ≥ 0:** el BiLSTM queda con peso **0**, es decir, no se usaría.
- **Motivo:** con los mismos datos, BETO ya capta lo que capta el BiLSTM y más (AUC por fragmento 0,81 frente a 0,56), y los dos se parecen poco (correlación de logits 0,28). El BiLSTM añade sobre todo ruido.

**Decisión de diseño (Orlando, 11 nov 2026): los dos modelos cuentan en el resultado unificado.** La propuesta de ScanTrue combina un modelo recurrente y un transformer. Por eso se fija por diseño el peso del BiLSTM y se mide su costo:

| Peso del BiLSTM | F1 art. (media pliegues) | Diferencia con BETO solo | Falsas alarmas |
| ---: | ---: | ---: | ---: |
| 0 % (BETO solo) | 0,733 | — | 7,5 % |
| 10 % | 0,729 | −0,004 | 7,5 % |
| **20 % (elegido)** | **0,719** | **−0,014** | **7,7 %** |
| 30 % | 0,713 | −0,020 | 7,7 % |
| 50 % | 0,693 | −0,040 | 8,0 % |

**El 20 % es el mayor peso probado cuya pérdida queda por debajo del margen de 0,02** que la regla común (§6) considera una diferencia no relevante. Con 30 % la pérdida llega al límite (−0,020). Hay que decirlo con honestidad: el bootstrap pareado por artículo indica que la pérdida de −0,014 frente a BETO solo es real (IC 95 % [−0,025; −0,005]), aunque pequeña. El BiLSTM entra en el resultado por decisión de diseño, no porque mejore la métrica.

Aun así, la combinación con 20 % es **mejor que lo que usa hoy la app** (+0,012 frente al 70/30, IC 95 % [+0,001; +0,024]) y mejor que el BiLSTM solo (+0,130).

## 4. Resultados (validación por fuente)

La temperatura (y los pesos aprendidos) se ajustan con dos fuentes y se miden en la tercera, rotando las tres. Todas las cifras son de la semilla 42 de cada modelo.

| Método | F1 art. (media pliegues) | Falsas alarmas art. | AUC frag. | Log-loss ↓ | Brier ↓ | ECE ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BiLSTM sin calibrar | 0,580 | 23,5 % | 0,569 | 1,393 | 0,302 | 0,276 |
| BiLSTM calibrado | 0,577 | 23,7 % | 0,563 | 0,665 | 0,235 | 0,149 |
| BETO sin calibrar | 0,732 | 7,5 % | 0,808 | 0,588 | 0,172 | 0,115 |
| BETO calibrado | 0,733 | 7,5 % | 0,807 | 0,480 | 0,157 | 0,015 |
| Media 70/30 actual (sin calibrar) | 0,708 | 8,2 % | 0,767 | 0,569 | 0,175 | 0,071 |
| Regresión logística libre | 0,698 | 6,7 % | 0,799 | 0,493 | 0,162 | 0,028 |
| Regresión con pesos ≥ 0 | 0,700 | 7,5 % | 0,798 | 0,495 | 0,163 | 0,030 |
| **Combinación 80/20 calibrada** | **0,719** | **7,7 %** | **0,803** | **0,488** | **0,159** | **0,028** |

Log-loss, Brier y ECE miden lo honestos que son los porcentajes: cuanto más bajos, mejor. La calibración baja el ECE de BETO de 0,115 a 0,015.

### Niveles de la extensión (§5.3)

Combinación elegida, validación por fuente, por fragmento:

| Nivel en la extensión | Fragmentos | % realmente falsas | Objetivo | Dentro |
| --- | ---: | ---: | --- | :---: |
| 0–20 «Muy probablemente verdadero» | 1.138 | 10 % | ≤ 20 % | ✅ |
| 21–40 «Probablemente verdadero» | 870 | 27 % | 20–40 % | ✅ |
| 41–60 «Resultado incierto» | 427 | 51 % | 40–60 % | ✅ |
| 61–80 «Probablemente falso» | 323 | 69 % | 60–80 % | ✅ |
| 81–100 «Muy probablemente falso» | 120 | 90 % | ≥ 80 % | ✅ |

Los niveles se asignan con la misma regla que la extensión: el porcentaje se redondea a entero y cae en el primer nivel cuyo tope no supera (20, 40, 60, 80, 100). Desde el 11 nov 2026 `tabla_niveles()` de `datos_comunes/evaluar_comun.py` usa esa regla; antes usaba `p < 0,2`, `p < 0,4`…, que solo cambiaba los casos en el borde.

Con la media 70/30 anterior, el último nivel tenía 245 fragmentos y solo el 75 % eran falsos (fuera de objetivo). La combinación calibrada lo usa menos (120), pero cuando lo usa acierta el 90 %.

## 5. Regla de discrepancia (§5.2)

Regla del plan: si un modelo da más de 0,5 y el otro menos, y se separan más que el umbral, el resultado se lleva a la franja «incierto» (0,4–0,6).

| Umbral | Fragmentos afectados | F1 art. | AUC frag. | Brier |
| --- | ---: | ---: | ---: | ---: |
| Sin regla | 0 | 0,725 | 0,803 | 0,159 |
| 0,4 | 314 | 0,723 | 0,787 | 0,166 |
| 0,5 | 76 | 0,726 | 0,801 | 0,160 |

Con 0,4 empeoran la ordenación y la calibración; con 0,5 casi no cambia nada. **Por ahora no se aplica** (`regla_discrepancia: null` en `combinacion.json`). Los resultados de cada modelo se siguen mostrando por separado en la extensión, así que el usuario ve cuándo discrepan. Si se quiere usar la regla para dar un papel más visible al BiLSTM, el umbral de 0,5 es el que no perjudica.

## 6. Archivos

| Archivo | Qué contiene | En Git |
| --- | --- | :---: |
| `datos_comunes/calibrar_conjunto.py` | Script: temperatura, combinación, validación por fuente, niveles, discrepancia y semillas | ✅ |
| `datos_comunes/tests/test_calibrar_conjunto.py` | Pruebas con datos sintéticos | ✅ |
| `datasets/comun_v1_corridas/calibracion/combinacion.json` | Parámetros que leerá el backend: temperaturas, pesos, umbral, semillas y SHA-256 de las entradas | — |
| `datasets/comun_v1_corridas/calibracion/RESUMEN.md` y `metricas.json` | Todas las tablas y métricas | — |
| `datasets/comun_v1_corridas/calibracion/predicciones_combinadas_fuera_de_pliegue.csv` | Probabilidad calibrada de cada modelo y combinada, por fragmento | — |
| `datasets/comun_v1_corridas/{bilstm,mbert}/final/contrato.json` | Temperatura definitiva; en mBERT, además, una sola semilla | — |
| `…/final/contrato_antes_calibracion.json` | Copia de cada contrato antes de este paso | — |

Para reproducirlo (tarda unos segundos en CPU, no hace falta GPU ni reentrenar):

```bash
bilstm/.venv/bin/python datos_comunes/calibrar_conjunto.py --sobrescribir
```

`--actualizar-contratos` vuelve a escribir la temperatura en los contratos. Con otro peso del BiLSTM hay que dar `--motivo`.

## 7. Límites y pendientes

- **Semilla 42 en los dos modelos.** Es la semilla del checkpoint final de cada uno. Las temperaturas se ajustan con los modelos de cada pliegue, que no son exactamente el modelo final entrenado con todo el desarrollo. La prueba congelada dirá si se mantienen.
- ✅ **Prueba congelada:** evaluada una sola vez el 11 nov 2026 con estos parámetros, sin ajustarlos después: combinación F1 0,826, cinco niveles dentro de objetivo. Ver [05_PRUEBA_CONGELADA.md](05_PRUEBA_CONGELADA.md).
- ✅ **Backend:** desde el 11 nov 2026 lee los dos contratos y `datasets/combinacion_produccion/combinacion.json` y aplica la fórmula de la sección 1 (sección 8).
- ✅ **Cortes de la extensión:** igualados el 11 nov 2026 (ver sección 4).

## 8. Paso a producción

Hecho el 11 de noviembre de 2026, con el mismo código que se evaluará en la prueba congelada.

| Qué | Dónde |
| --- | --- |
| BiLSTM B6 (semilla 42) | `datasets/bilstm_produccion/modelo/`: `modelo.pt`, `config.json`, `resultados.json` y `contrato.json` |
| BETO M3b (semilla 42) | `datasets/mbert_produccion/modelo/`: `best_model/` (pesos con Git LFS y tokenizador), `config.json`, `resultados.json` y `contrato.json` |
| Combinación | `datasets/combinacion_produccion/combinacion.json` (copia de `datasets/comun_v1_corridas/calibracion/combinacion.json`) |
| Modelos de octubre | Sin borrar ni usar, en `datasets/bilstm_produccion/archivo_octubre/` y `datasets/mbert_produccion/archivo_octubre/` |
| Métricas de la extensión | `backend/metrics/*.json`, generadas con `datos_comunes/publicar_metricas.py`. Las de octubre, en `backend/metrics/archivo_octubre/` |

Los contratos de producción son los de `datasets/comun_v1_corridas/{bilstm,mbert}/final/` con las rutas cambiadas a las carpetas de producción y el campo `origen`.

**Backend** (detalle en [backend/docs/CAMBIO_MODELOS_CALIBRADOS.md](../../backend/docs/CAMBIO_MODELOS_CALIBRADOS.md)):

- `backend/models/contrato.py` lee los contratos y la combinación, verifica los SHA-256 y comprueba que la versión y la temperatura de cada contrato coinciden con las de la combinación. Si no coinciden, el backend no arranca el análisis: hay que recalibrar.
- `backend/models/bilstm.py` y `backend/models/mbert.py` devuelven la probabilidad **calibrada** de cada modelo, con el orden de clases del contrato (0 = real, 1 = falsa).
- `backend/services/analysis.py` combina con `sigmoide(0,2 · logit(p_bilstm) + 0,8 · logit(p_beto))`. Si solo responde un modelo, usa su probabilidad. `ANALYSIS_MBERT_WEIGHT` ya no se usa.
- Cada modelo lee hasta su propio límite: BETO 256 subpalabras y BiLSTM 192 palabras. Antes, el BiLSTM recibía el recorte de BETO, y en un 32 % de los fragmentos largos eso le dejaba menos de 192 palabras.
- La respuesta mantiene `version_regla = "media_ponderada_v1"`, porque la base de datos solo acepta ese valor, y añade `version_combinacion`.
- Se comprobó que el backend reproduce los logits del entrenamiento: BiLSTM exacto; BETO con diferencias de hasta 0,024 en el logit, por BF16 en GPU.

**Extensión:** el segundo modelo se muestra como «BETO»; el medidor de longitud llega a ~200 palabras (lo que leen los dos modelos); los conjuntos de métricas nuevos tienen nombre propio.

