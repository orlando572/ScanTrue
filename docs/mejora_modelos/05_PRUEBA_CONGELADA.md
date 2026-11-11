# Prueba congelada

**Fecha:** 11 de noviembre de 2026, 15:28 · **Evaluada una sola vez**, por decisión de Orlando, con los modelos, la calibración y la combinación ya fijados ([01_PLAN_COMUN.md §6](01_PLAN_COMUN.md#6-reglas-de-decisión-fijadas-antes-de-entrenar)). No se ha ajustado nada después.
**Script:** [`datos_comunes/prueba_congelada.py`](../../datos_comunes/prueba_congelada.py), con el mismo código que usa la app (`backend/models/`).
**Resultados completos (fuera de Git):** `datasets/comun_v1_corridas/prueba_congelada/` (`RESUMEN.md`, `metricas.json`, predicciones de cada modelo en el formato común y probabilidades calibradas).

## 1. Qué se evaluó

- **Datos:** `fragmentos_prueba_congelada.csv` de `comun_v1.1`: **555 fragmentos de 310 artículos**. Es el 15 % de los grupos de v1, FakeDeS y Polyglot, más FalleDesinfo completo.
- **Modelos:** BiLSTM B6 (`comun_v1.1_B6_20261107`) y BETO M3b (`comun_v1.1_M3b_20261111`), semilla 42, con la temperatura de su contrato.
- **Combinación:** 80 % BETO + 20 % BiLSTM sobre logits calibrados (`comun_v1.1_conjunta_20261111`).
- **Métrica:** F1 macro por artículo (media de las probabilidades de sus fragmentos), umbral 0,5, IC 95 % por bootstrap de artículos.

## 2. Resultados

| Modelo | F1 macro art. | IC 95 % | Falsas alarmas art. | AUC frag. | Brier frag. | Validación por fuente (referencia) |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| BiLSTM B6 | 0,678 | [0,620; 0,733] | 16,9 % | 0,707 | 0,206 | 0,595 |
| BETO M3b | **0,829** | [0,781; 0,874] | **2,0 %** | **0,889** | **0,110** | 0,739 |
| **Combinación 80/20 (la que usa la app)** | **0,826** | [0,778; 0,871] | 2,5 % | 0,887 | 0,110 | 0,725 |

Por fuente (F1 macro por artículo):

| Modelo | v1 (96) | FakeDeS (79) | Polyglot (103) | **FalleDesinfo (32)** |
| --- | ---: | ---: | ---: | ---: |
| BiLSTM B6 | 0,667 | 0,592 | 0,780 | 0,396 |
| BETO M3b | 0,816 | 0,830 | 0,892 | 0,407 |
| Combinación | 0,816 | 0,818 | 0,892 | 0,407 |

Niveles de la extensión con la combinación (por fragmento):

| Nivel | Fragmentos | % realmente falsas | Objetivo | Dentro |
| --- | ---: | ---: | --- | :---: |
| 0–20 «Muy probablemente verdadero» | 351 | 11 % | ≤ 20 % | ✅ |
| 21–40 «Probablemente verdadero» | 58 | 29 % | 20–40 % | ✅ |
| 41–60 «Resultado incierto» | 26 | 54 % | 40–60 % | ✅ |
| 61–80 «Probablemente falso» | 39 | 77 % | 60–80 % | ✅ |
| 81–100 «Muy probablemente falso» | 81 | 95 % | ≥ 80 % | ✅ |

## 3. Cómo leerlo

1. **Por qué sube respecto a la validación por fuente (0,83 frente a 0,73).** Los artículos de v1, FakeDeS y Polyglot de la prueba congelada son de fuentes que los modelos finales **sí vieron** al entrenar: solo se apartaron sus grupos, no la fuente entera. La validación dejando una fuente fuera mide otra cosa, más difícil: una fuente nunca vista. **Para noticias de medios nuevos, la cifra de referencia sigue siendo la validación por fuente (BETO 0,739, combinación 0,725).**
2. **FalleDesinfo es la única fuente realmente nueva, y ahí los modelos fallan.** Son 32 artículos (22 reales, 10 falsos). Ningún modelo detecta ninguna de las 10 falsas: BETO da a todos sus fragmentos menos de 0,38, y el AUC queda por debajo de 0,5 (0,36–0,40). La muestra es pequeña, pero el resultado es claro: con un medio y un tema que no vieron, los modelos no reconocen la desinformación.
3. **Los modelos son conservadores.** La combinación marca como falsas muy pocas reales (2,5 % de falsas alarmas), pero deja pasar falsas: detecta 69 de 109 artículos falsos (63 %). El umbral sigue en 0,5, como se fijó.
4. **Los porcentajes son honestos.** Los cinco niveles de la extensión quedan dentro de su objetivo también aquí. «Muy probablemente falso» acierta el 95 %; con el 70/30 sin calibrar de octubre, en la validación por fuente acertaba el 75 %.
5. **La combinación cuesta muy poco frente a BETO solo:** −0,003 de F1 y +0,5 puntos de falsas alarmas. Va en la línea de lo medido en la calibración (§3 de [04_CALIBRACION_CONJUNTA.md](04_CALIBRACION_CONJUNTA.md)). Con el BiLSTM al 20 %, los dos modelos cuentan sin perjudicar de forma apreciable el resultado.
6. **El BiLSTM solo** (0,678) supera su propia validación por fuente (0,595), pero tiene 16,9 % de falsas alarmas, sobre todo en FakeDeS (37 %).

## 4. Consecuencias

- La prueba congelada **ya no es inédita**. Cualquier cambio futuro de modelos, pesos o umbral necesitará datos nuevos para evaluarse; no se puede volver a usar esta prueba para elegir.
- Las cifras se publican en la extensión (`GET /metricas`) junto con la validación por fuente y un apartado para FalleDesinfo (`datos_comunes/publicar_metricas.py`).
- El límite principal es la **generalización a medios nuevos**. Para mejorarla harían falta datos de más fuentes, no más ajustes con estas.
