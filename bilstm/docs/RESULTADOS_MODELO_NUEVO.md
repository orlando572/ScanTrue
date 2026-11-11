# BiLSTM con el conjunto común `comun_v1`: experimentos B0–B8

**Fecha:** 7 de noviembre de 2026
**Plan:** [02_PLAN_BILSTM.md](../docs/mejora_modelos/02_PLAN_BILSTM.md) y [01_PLAN_COMUN.md](../docs/mejora_modelos/01_PLAN_COMUN.md).
**Estado (v1.0, ver §0 para v1.1):** B0–B8 ejecutados, modelo final entrenado y temperatura **provisional**. La prueba congelada **no** se ha abierto. El backend no se ha tocado.

## 0. Actualización: conjunto `comun_v1.1` (7 nov 2026)

`comun_v1.1` quita 8 artículos falsos de Polyglot que no estaban en español (inglés, francés o italiano). El resto del conjunto queda idéntico, fragmento por fragmento. Se repitió todo el plan (B0–B8, referencias y etapa final) con el mismo código. Las métricas de la versión 1.0 quedan en `datasets/comun_v1_corridas/respaldo_v1.0/` (sin checkpoints).

| | v1.0: F1 | v1.0: FA | v1.1: F1 | v1.1: FA |
| --- | ---: | ---: | ---: | ---: |
| B0 (receta actual) | 0,524 | 29,9 % | **0,497** | **19,1 %** |
| B6 (+usmsc) | 0,582 | 26,1 % | 0,585 | 27,9 % |
| TF-IDF caracteres 3–5 | 0,561 | 19,2 % | 0,554 | 18,9 % |
| Solo longitud | 0,532 | 42,4 % | 0,533 | 42,3 % |

- **B6 es estable** (0,582 → 0,585). **B0 no lo es:** baja 0,027 y cambia mucho su tasa de falsas alarmas al quitar el 0,4 % de los artículos. El entrenamiento es determinista (repetir una corrida da logits idénticos), así que el cambio viene de los datos, sobre todo de la validación interna que elige la época, no del azar de la GPU.
- **La regla fijada ahora rechaza B6:** sube F1 en +0,088, pero las falsas alarmas suben 8,8 puntos frente a B0 (el límite es 2). Por eso `decisiones.json` y `final/` de v1.1 contienen **B0**, y B0 pierde con claridad contra TF-IDF: −0,055, IC 95 % [−0,084; −0,022].
- **B6 frente a TF-IDF en v1.1:** +0,029, IC 95 % [−0,002; 0,058], P(B6 mejor) = 0,97, pero con 9 puntos más de falsas alarmas.
- **Lectura:** las diferencias de B0 entre versiones son del mismo tamaño que el umbral de 0,02, así que la regla aplicada contra un B0 inestable no es fiable.
- **Decisión (7 nov 2026): se elige B6 a mano**, apartándose de la regla. Motivo: es estable entre versiones y tiene el mejor F1; las falsas alarmas se miden con el umbral fijo de 0,5, que se ajustará en la calibración conjunta con mBERT. La elección y su motivo quedan en `final/contrato.json` (`eleccion`). El modelo final que daba la regla (B0) se conserva en `final_B0_por_regla/`.
- **Modelo final v1.1:** B6, semilla 42, 4 épocas (mediana de los pliegues), `entrenar.py final --ganador B6`. Temperatura provisional **T = 8,45**. Fuera de pliegue, por artículo y calibrado: F1 0,596, falsas alarmas 23,7 %, AUC 0,593, Brier 0,233. Por fragmento, los niveles calibrados quedan así: 0–20 % tiene 5 fragmentos; 20–40 % tiene 1.014 (29 % falsas, dentro del objetivo); 40–60 % tiene 1.621 (30 % falsas); 60–80 % tiene 238 (52 % falsas); 80–100 % ninguno.

El resto de este documento describe la versión 1.0.

## 1. Resumen

- **Ganador: B6 = receta B0 + brazo `+usmsc`.** F1 macro de artículo **0,582 ± 0,021** (media de pliegues y semillas), frente a 0,524 de B0. Falsas alarmas de artículo 26,1 % (B0: 29,9 %).
- Ningún cambio de arquitectura ayudó: pooling max+media (+0,003), embeddings congelados (−0,014), oculto 128 (−0,021) y 320 tokens (+0,001) no pasan la regla.
- **Frente a TF-IDF de caracteres** (0,561): el BiLSTM gana **+0,022** en la métrica de selección, justo por encima del umbral de 0,02 de [02_PLAN_BILSTM.md §4](../docs/mejora_modelos/02_PLAN_BILSTM.md). Pero en el bootstrap pareado por artículo la diferencia es **+0,015, IC 95 % [−0,015; 0,045]**: **no es concluyente**. Ver sección 6.
- **Temperatura T = 8,83 (provisional).** El modelo está muy sobreconfiado. Calibrado, ningún fragmento cae en «Muy probablemente verdadero» ni en «Muy probablemente falso»; los niveles 40–60 y 60–80 quedan por debajo de su objetivo (34 % y 47 % de falsas).
- La validación por fuente es dura: todas las cifras están entre 0,50 y 0,61. Es lo esperado según [01_PLAN_COMUN.md §9](../docs/mejora_modelos/01_PLAN_COMUN.md).

## 2. Conjunto común `datasets/comun_v1/`

Construido con [`datos_comunes/construir_comun.py`](../datos_comunes/construir_comun.py); detalle completo en `datasets/comun_v1/REPORTE.md` y `manifest.json`. Reconstruirlo da archivos byte a byte idénticos.

| Archivo | Filas | Contenido |
| --- | ---: | --- |
| `fragmentos_desarrollo.csv` | 2.888 | 1.575 artículos de v1, FakeDeS y Polyglot (F1/F2/F3) |
| `fragmentos_prueba_congelada.csv` | 556 | 15 % de los grupos (estratificado por fuente y clase) + FalleDesinfo. **No abierto** |
| `ablacion_satira.csv` | 345 | 301 artículos de sátira de v1, fragmentados |
| `ablacion_usmsc.csv` | 1.684 | USMSC/Edds residual, sin fragmentar (≈ 43 tokens) |
| `ablacion_politica.csv` | 2.000 | 1.000 parejas real/falsa con el mismo titular, una por grupo |

Desarrollo por pliegue: F1 (v1) 544 artículos / 778 fragmentos; F2 (FakeDeS) 444 / 805; F3 (Polyglot) 587 / 1.305.

**Decisiones y desviaciones respecto al plan:**

- **Se quitó la marca `*NUMBER*` del corpus v1.** Sustituye todas las cifras de v1 (en el 88 % de las reales y el 59 % de las falsas sin sátira), así que identificaba la fuente e incluso la clase dentro de v1. No estaba en la lista de §3.2, pero es una marca de procedencia; las cifras originales no se pueden recuperar.
- **Patrones de limpieza** (revisados a mano, con ejemplos en `REPORTE.md`): datelines («México.-», «MÉXICO, D.F. (apro).-», «Kiev, Ucrania, 31 Dic 2022 (AFP) -»), URLs y `pic.twitter.com`, menciones `@`, hashtags de cierre, créditos de foto, firmas «Por …», «Con información de …», pies fijos de El Mundo (Trust Project 397 reales, «Hazte Premium» 59, etiqueta de opinión 8), «FuenteNoticias relevantes no encontradas» (130 falsas de Polyglot), descargo de RT, «¡compártelo con tus amigos!» y comillas escapadas `'"'"` (427 reales de Polyglot).
- **Artículos de menos de 100 tokens descartados: 106** (92 en el análisis previo; la limpieza quita algunos tokens).
- **Fragmentos: 3.444 en total, no 4.000–5.000.** Con tamaños sorteados entre 100 y 400 (media 250) y fragmentos sin solapar, un artículo de 450 palabras da 1–2 fragmentos. En el desarrollo, 854 artículos dan 1 fragmento, 342 dan 2, 166 dan 3 y 213 dan 4.
- **Tope de 400 tokens mantenido.** La referencia de solo longitud queda en F1 macro de artículo **0,532** (AUC 0,58), frente a 0,663 / 0,717 de la prueba externa antigua. Comprobación de sensibilidad con tope 300: 0,519. La diferencia es mínima y 300 impediría medir B8.
- **Agrupación:** grupos del unificado (huella, titular, cuerpo, URL) + URL sin esquema + casi duplicados por tejas de 5 palabras (contención ≥ 0,65). Un grupo del desarrollo cruza dos fuentes; el cargador ([`datos_comunes/comun.py`](../datos_comunes/comun.py)) quita del entrenamiento todo grupo presente en la fuente que queda fuera.
- **Sátira de v1:** lleva `fuente = v1`, así que no entra al entrenar F1. Las 8 filas de sátira de FakeDeS se excluyen.
- **Aviso:** en FakeDeS las 72 filas sin titular son todas falsas. El primer fragmento de las reales empieza con titular; no se puede corregir sin inventar titulares.

## 3. Reglas fijadas antes de ejecutar B1–B8

- **Métrica de selección:** media de F1 macro de artículo de los tres pliegues, promediada en las semillas 42, 43 y 44. La probabilidad de un artículo es la media de las de sus fragmentos.
- **Se adopta un cambio** si esa media sube **≥ 0,02** respecto al ganador vigente y la tasa de falsas alarmas de artículo no sube más de **2 puntos**.
- **Brazos (B5–B7):** además deben mejorar F1 en **al menos dos de los tres pliegues**.
- **B2** solo se prueba si B1 se adopta.
- La regla se aplicó de forma automática con `bilstm/entrenar.py plan` (antes `plan_comun.py` y `decidir_comun.py`).

**Receta B0:** fastText CC 300 d ajustable → BiLSTM 1 capa, 64 por dirección → estado final → lineal; 192 tokens; AdamW lr 1e-3, decaimiento 0,01; lote 32; dropout 0,3; ReduceLROnPlateau (0,5, paciencia 2); máximo 20 épocas, paciencia 5 con la validación interna (10 % de los grupos de entrenamiento, F1 macro de artículo). Pérdida por muestra × `peso` × peso de clase. Neurona 1 = falsa.

## 4. Registro de experimentos

Cada fila son 9 corridas (3 pliegues × 3 semillas) en GPU. Δ respecto al ganador vigente.

| ID | Cambio | F1 macro art. (media ± desv. semillas) | Falsas alarmas | F1 (v1) | F2 (FakeDeS) | F3 (Polyglot) | AUC art. | Δ F1 | Δ FA (pts) | Pliegues que mejoran | Decisión |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| B0 | Receta actual con `comun_v1` | 0,524 ± 0,007 | 0,299 | 0,536 | 0,520 | 0,514 | 0,525 | — | — | — | Línea base |
| B1 | Pooling max + media | 0,527 ± 0,012 | 0,395 | 0,537 | 0,521 | 0,523 | 0,560 | +0,003 | +9,7 | 3/3 | Rechazado |
| B2 | Pooling con atención | — | — | — | — | — | — | — | — | — | No se ejecuta: B1 no se adoptó |
| B3 | Embeddings congelados 3 épocas, después lr × 0,1 | 0,509 ± 0,002 | 0,280 | 0,530 | 0,485 | 0,514 | 0,515 | −0,014 | −1,9 | 0/3 | Rechazado |
| B4 | Oculto 128 | 0,503 ± 0,010 | 0,311 | 0,514 | 0,509 | 0,485 | 0,507 | −0,021 | +1,2 | 0/3 | Rechazado |
| B5 | `+satira` | 0,526 ± 0,012 | 0,332 | 0,536 | 0,557 | 0,484 | 0,554 | +0,002 | +3,3 | 1/3 | Rechazado |
| **B6** | **`+usmsc`** | **0,582 ± 0,021** | **0,261** | **0,580** | **0,610** | **0,558** | **0,623** | **+0,059** | **−3,8** | **3/3** | **Adoptado** |
| B7 | B6 + `+politica` | 0,550 ± 0,014 | 0,296 | 0,576 | 0,545 | 0,528 | 0,579 | −0,033 | +3,6 | 0/3 | Rechazado |
| B8 | B6 con 320 tokens | 0,583 ± 0,007 | 0,260 | 0,571 | 0,612 | 0,567 | 0,623 | +0,001 | 0,0 | 2/3 | Rechazado: se queda 192 (más barato) |
| ref | Solo longitud | 0,532 | 0,424 | 0,491 | 0,535 | 0,571 | 0,577 | | | | Referencia |
| ref | TF-IDF caracteres 3–5 + RL | 0,561 | 0,192 | 0,605 | 0,535 | 0,542 | 0,613 | | | | Referencia |

Notas:

- **B5:** en F1 la sátira no entra (es de v1), así que solo puede influir en F2 y F3; mejora F2 y empeora F3.
- **B6, comprobación de fuga:** 33 de las 1.684 filas de USMSC se parecen a artículos del desarrollo (27 contienen una ventana de 60 letras de un artículo de FakeDeS o v1). Las 33 comparten grupo con ese artículo, así que el cargador las quita cuando su fuente queda fuera. La mejora no viene de copias.
- **Sobreajuste:** la pérdida de entrenamiento llega a ~0 en 5–8 épocas y la validación interna (0,75–0,88 en F1/F2) no predice la fuente externa (~0,55). Las épocas elegidas en B6 fueron 2–11 (mediana 5).
- B0 y B1 de v1.0 se corrieron con la versión de `entrenar_comun.py` (hoy `entrenar.py corrida`) anterior a admitir varios brazos (`--brazo` con `nargs`). El comportamiento sin brazos es idéntico; el hash del script queda registrado en cada `config.json`.

## 5. Ganador B6 por pliegue y fuente

Cada pliegue valida en una sola fuente. Media ± desviación de las 3 semillas.

**Nivel de artículo**

| Pliegue (fuente) | Artículos | F1 macro | F1 falsa | Precisión falsa | Recall falsa | Falsas alarmas | AUC | AP | Brier | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| F1 (v1) | 544 | 0,580 ± 0,010 | 0,418 ± 0,047 | 0,345 ± 0,011 | 0,539 ± 0,134 | 0,323 ± 0,072 | 0,642 ± 0,031 | 0,379 | 0,268 | 0,270 |
| F2 (FakeDeS) | 444 | 0,610 ± 0,019 | 0,561 ± 0,017 | 0,589 ± 0,028 | 0,537 ± 0,015 | 0,317 ± 0,034 | 0,621 ± 0,026 | 0,606 | 0,300 | 0,237 |
| F3 (Polyglot) | 587 | 0,558 ± 0,038 | 0,375 ± 0,106 | 0,600 ± 0,074 | 0,296 ± 0,151 | 0,142 ± 0,113 | 0,607 ± 0,029 | 0,512 | 0,259 | 0,145 |

**Nivel de fragmento**

| Pliegue (fuente) | Fragmentos | F1 macro | F1 falsa | Precisión falsa | Recall falsa | Falsas alarmas | AUC | AP | Brier | ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| F1 (v1) | 778 | 0,544 ± 0,003 | 0,354 ± 0,035 | 0,266 ± 0,008 | 0,538 ± 0,130 | 0,352 ± 0,070 | 0,616 ± 0,030 | 0,274 | 0,297 | 0,302 |
| F2 (FakeDeS) | 805 | 0,596 ± 0,018 | 0,505 ± 0,020 | 0,473 ± 0,021 | 0,541 ± 0,021 | 0,340 ± 0,018 | 0,629 ± 0,020 | 0,483 | 0,316 | 0,286 |
| F3 (Polyglot) | 1.305 | 0,547 ± 0,012 | 0,368 ± 0,065 | 0,466 ± 0,030 | 0,319 ± 0,116 | 0,211 ± 0,104 | 0,603 ± 0,005 | 0,449 | 0,273 | 0,190 |

Matrices de confusión de artículo, semilla 42, orden `[real, falsa]`: F1 `[[305, 108], [77, 54]]`, F2 `[[161, 80], [91, 112]]`, F3 `[[333, 24], [180, 50]]`.

**Predicciones fuera de pliegue juntas** (los 1.575 artículos), F1 macro de artículo con IC 95 % por bootstrap de artículos (1.000 remuestreos): semilla 42 **0,588 [0,563; 0,613]**, semilla 43 0,610 [0,583; 0,635], semilla 44 0,577 [0,551; 0,602].

## 6. Comparación con la referencia TF-IDF

| Medida | BiLSTM B6 | TF-IDF | Diferencia |
| --- | ---: | ---: | ---: |
| Media de F1 macro de artículo en los pliegues (selección) | 0,582 | 0,561 | **+0,022** |
| F1 macro de artículo fuera de pliegue, semilla 42 vs TF-IDF (bootstrap pareado, 1.575 artículos) | 0,588 | 0,573 | +0,015, IC 95 % [−0,015; 0,045]; P(BiLSTM mejor) = 0,83 |
| Falsas alarmas de artículo (media de pliegues) | 0,261 | 0,192 | +6,9 puntos |

Según la regla de §4 del plan, el BiLSTM **se mantiene** porque supera al TF-IDF en ≥ 0,02. Pero lo supera por muy poco, con un intervalo que incluye el empate y más falsas alarmas. **Queda a decisión de Orlando**: el TF-IDF calibrado es más pequeño, rápido y explicable, y podría ocupar el mismo contrato (`probabilidad_falsa`). El TF-IDF se probó sin el brazo `+usmsc`; no se ha medido si ese brazo también lo mejora.

## 7. Modelo final y calibración

- **Entrenamiento:** configuración B6 con todo el desarrollo + `ablacion_usmsc.csv` (sin grupos de la prueba congelada), **5 épocas** (mediana de las 9 corridas), semilla 42.
- **Semillas:** promediar los logits de 3 semillas da 0,579 frente a 0,582 de las semillas por separado; la ganancia es menor de 0,01, así que se usa **una sola semilla (42)**.
- **Temperatura:** **T = 8,83**, ajustada minimizando el log-loss con las 2.888 predicciones fuera de pliegue de la semilla 42. Marcada como `temperatura_provisional: true` en el contrato hasta calibrar junto con mBERT. No cambia el orden ni la clase con umbral 0,5.

| Fragmentos fuera de pliegue (semilla 42) | Brier | ECE (10 tramos) | F1 macro | AUC |
| --- | ---: | ---: | ---: | ---: |
| Sin calibrar | 0,309 | 0,286 | 0,570 | 0,599 |
| Con T = 8,83 | 0,225 | 0,109 | 0,570 | 0,599 |

### Tabla de niveles de la extensión (§5.3), solo BiLSTM

Fragmentos fuera de pliegue, semilla 42. La combinación con mBERT aún no existe.

| Nivel en la extensión | Sin calibrar: fragmentos | Sin calibrar: % falsas | Con T: fragmentos | Con T: % falsas | Objetivo | ¿Cumple (con T)? |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 0–20 «Muy probablemente verdadero» | 1.817 | 26,3 % | 0 | — | ≤ 20 % | Vacío |
| 20–40 «Probablemente verdadero» | 196 | 33,2 % | 1.435 | 25,0 % | 20–40 % | Sí |
| 40–60 «Resultado incierto» | 135 | 38,5 % | 1.066 | 34,2 % | 40–60 % | No (por debajo) |
| 60–80 «Probablemente falso» | 147 | 32,0 % | 387 | 47,3 % | 60–80 % | No (por debajo) |
| 80–100 «Muy probablemente falso» | 593 | 44,9 % | 0 | — | ≥ 80 % | Vacío |

Por fuente, con T (fragmentos y % de falsas en 20–40 / 40–60 / 60–80): v1 346 (14 %) / 326 (22 %) / 106 (28 %); FakeDeS 305 (24 %) / 301 (36 %) / 199 (54 %); Polyglot 784 (30 %) / 439 (42 %) / 82 (55 %).

**Lectura:** sin calibrar, el nivel «Muy probablemente falso» acierta solo el 45 % de las veces. Con T, los porcentajes dejan de mentir en los extremos porque ya no se muestran, pero el modelo nunca llega a 80 % de forma honesta, como anticipaba §5.3. El 31 % de los fragmentos son falsos, así que «Resultado incierto» por debajo de 40 % refleja esa proporción base.

### Contrato propuesto

`datasets/comun_v1_corridas/bilstm/final/contrato.json`:

```json
{
  "modelo": "bilstm",
  "version": "comun_v1_B6_20261107",
  "etiquetas": {"real": 0, "falsa": 1},
  "max_tokens": 192,
  "pooling": "final",
  "hidden_dim": 64,
  "temperatura": 8.8316,
  "temperatura_provisional": true,
  "umbral_falsa": 0.5,
  "semillas": [42],
  "promediar_logits_semillas": false,
  "epocas": 5,
  "checkpoints": {"s42": {"ruta": "datasets/comun_v1_corridas/bilstm/final/todo_s42/modelo.pt", "sha256": "edd5eb27…"}},
  "sha256_conjunto": "eddd77ee…"
}
```

## 8. Entregables

| Ruta | Contenido |
| --- | --- |
| `datasets/comun_v1/` | Conjunto común, `manifest.json`, `REPORTE.md`, `pliegues.json` |
| `datasets/comun_v1_corridas/referencias/` | Predicciones y métricas de las dos referencias |
| `datasets/comun_v1_corridas/bilstm/B*/` | 9 corridas por experimento (`config.json`, `resultados.json`, `predicciones.csv`; los `modelo.pt` se borraron en la limpieza del 10 nov 2026) y `evaluacion/metricas.json` |
| `datasets/comun_v1_corridas/bilstm/decisiones.json` | Registro de decisiones |
| `datasets/comun_v1_corridas/bilstm/final/` | Checkpoint final, `contrato.json`, `resumen_final.json`, `predicciones_fuera_de_pliegue.csv` (B6, 3 semillas) y su media de semillas |

Código: [`datos_comunes/`](../../datos_comunes/) (conjunto común, evaluación y referencias), [`bilstm/entrenar.py`](../entrenar.py) (único script de entrenamiento), [`bilstm/modelo.py`](../modelo.py) y [`bilstm/tests/`](../tests/). El 10 nov 2026 los scripts `entrenar_comun.py`, `serie_comun.py`, `plan_comun.py`, `decidir_comun.py` y `final_comun.py` se unieron en `entrenar.py` sin cambiar resultados (una corrida repetida da logits idénticos); los originales están en el historial de Git (commit `d4ece74`).

## 9. Pendiente

- Decidir BiLSTM o TF-IDF (sección 6).
- Calibrar y combinar con mBERT (paso 4 del plan común); recalcular T y la tabla de niveles con la combinación.
- Cambiar el backend a la convención `etiqueta_falsa` y al contrato (paso 5). No se tocaron en esta fase.
- Prueba congelada, una sola vez, con todo ya fijado.

## 10. Cómo reproducir

```bash
bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
bilstm/.venv/bin/python -m unittest discover -s bilstm/tests
bilstm/.venv/bin/python datos_comunes/construir_comun.py
bilstm/.venv/bin/python datos_comunes/referencias.py --salida datasets/comun_v1_corridas/referencias
bilstm/.venv/bin/python datos_comunes/evaluar_comun.py --predicciones datasets/comun_v1_corridas/referencias/*/predicciones.csv --salida datasets/comun_v1_corridas/referencias/evaluacion
bilstm/.venv/bin/python bilstm/entrenar.py plan
bilstm/.venv/bin/python bilstm/entrenar.py final --ganador B6 --motivo "…"
```
