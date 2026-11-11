# Resultados del modelo nuevo (comun_v1.1)

Experimentos de la fase E del plan ([03_PLAN_MBERT.md §7](../../docs/mejora_modelos/03_PLAN_MBERT.md)), ejecutados el 11 nov 2026 con `mBERT/entrenar.py plan` en una RTX 5060 Laptop (8 GB, BF16).

- **Datos:** `datasets/comun_v1/` v1.1, SHA-256 de `fragmentos_desarrollo.csv` = `c13a9721648a864177d8a1e85de6f5e7e0823430596c3dd75e5d43da0e14aff9`. Etiquetas `real = 0`, `falsa = 1`.
- **Validación:** dejar una fuente fuera (F1 = v1, F2 = fakedes, F3 = polyglot) y 3 semillas (42, 43, 44). Son 9 corridas por experimento.
- **Métrica:** F1 macro por artículo. Se calcula la media de los 3 pliegues para cada semilla y después la media y la desviación entre semillas. FA es la tasa de falsas alarmas (reales marcadas como falsas).
- **Regla:** se adopta un cambio si la F1 sube al menos 0,02 y la FA no sube más de 2 puntos. Un brazo, además, debe mejorar al menos 2 de los 3 pliegues.
- **Nunca se ha abierto** `fragmentos_prueba_congelada.csv`. No se han usado el conjunto externo de 569, la prueba de 146 ni la validación de 132.
- **Registro completo:** `datasets/comun_v1_corridas/mbert/decisiones.json`. Cada corrida está en `datasets/comun_v1_corridas/mbert/<ID>/F?_s?/`.

## Resultado

**Ganador: M3b, BETO (`dccuchile/bert-base-spanish-wwm-cased`) más el brazo `usmsc`, con la receta base.** La receta base usa 256 tokens, lr 2e-5, hasta 3 épocas, decaimiento 0,01, calentamiento 10 %, lote efectivo 16 y pesos por muestra.

| | F1 | FA |
| --- | --- | --- |
| **M3b (ganador)** | **0,721 ± 0,011** | **11,2 %** |
| M0, mBERT con la receta actual | 0,568 ± 0,023 | 24,4 % |
| BiLSTM B6 | 0,585 | — |
| TF-IDF de caracteres | 0,554 | — |
| Solo longitud | 0,533 | — |

Frente a B6, el ganador sube la F1 en **+0,136**. Los valores de B6, TF-IDF y longitud vienen del plan (§2). La carpeta `datasets/comun_v1_corridas/referencias/` no está en esta copia, así que todavía no se han comparado las predicciones corrida a corrida.

## Todos los experimentos

| ID | Configuración | F1 (± desv.) | FA | F1 / F2 / F3 | Semillas 42 / 43 / 44 | Decisión |
| --- | --- | --- | --- | --- | --- | --- |
| M0 | mBERT, receta actual | 0,568 ± 0,023 | 24,4 % | 0,575 / 0,573 / 0,557 | 0,594 / 0,555 / 0,554 | línea base |
| M1a | BETO | 0,672 ± 0,025 | 19,3 % | 0,701 / 0,628 / 0,687 | 0,657 / 0,702 / 0,658 | **gana el paso 1** |
| M1b | MarIA | — | — | — | — | omitido (sin pesos) |
| M1c | XLM-R | 0,645 ± 0,025 | 12,2 % | 0,644 / 0,632 / 0,661 | 0,666 / 0,652 / 0,618 | pierde frente a M1a |
| M2a | M1a + lr 1e-5, hasta 5 épocas | 0,679 ± 0,010 | 18,4 % | 0,718 / 0,621 / 0,697 | 0,668 / 0,687 / 0,682 | rechazado (+0,007) |
| M2b | M1a + lr 3e-5, 3 épocas | 0,633 ± 0,071 | 27,9 % | 0,687 / 0,600 / 0,611 | 0,552 / 0,683 / 0,664 | rechazado (−0,039) |
| M2c | M1a + 512 tokens | 0,667 ± 0,019 | 16,3 % | 0,702 / 0,610 / 0,689 | 0,668 / 0,686 / 0,647 | rechazado (−0,005) |
| M3b | M1a + brazo `usmsc` | 0,721 ± 0,011 | 11,2 % | 0,771 / 0,697 / 0,696 | 0,732 / 0,710 / 0,721 | **adoptado** (+0,049, mejora los 3 pliegues) |
| M3a | M3b + brazo `satira` | 0,709 ± 0,007 | 15,5 % | 0,764 / 0,707 / 0,657 | 0,713 / 0,702 / 0,714 | rechazado (−0,012, mejora 1 pliegue) |
| M3c | M3b + brazo `politica` | 0,679 ± 0,025 | 14,2 % | 0,693 / 0,671 / 0,673 | 0,658 / 0,672 / 0,707 | rechazado (−0,042, mejora 0 pliegues) |

## Decisiones y motivos

### Paso 0
- **M0-len.** Fracción de fragmentos truncados a 256 tokens: mBERT 62,1 %, BETO 53,9 %, XLM-R 60,1 %. A 512 tokens: 8,7 %, 1,3 % y 6,0 %.

### Paso 1
- **1R, prueba rápida con la semilla 42.** BETO sacó 0,657 frente a 0,594 de M0 (+0,062), así que se completaron sus semillas 43 y 44.
- **M1b (MarIA) se omite** por decisión del 11 nov 2026. El repositorio oficial `PlanTL-GOB-ES/roberta-base-bne` está retirado y no tiene pesos, y `BSC-LT/roberta-base-bne` no existe.
- **Gana BETO (M1a).** Supera a XLM-R por 0,027, de modo que no hay empate y no hace falta la preferencia por tamaño. Hay un conflicto que se consultó antes de seguir: BETO tiene 7,1 puntos más de FA que XLM-R (19,3 % frente a 12,2 %). La regla solo limita la FA frente al ganador anterior (M0, 24,4 %), y ahí BETO la baja. **El 11 nov 2026 se confirmó BETO, de acuerdo con la regla.** Además, BETO es más pequeño (110 M de parámetros frente a 278 M) y tarda menos (14 min frente a 18 min por experimento).

### Paso 2
- **M2a y M2b se rechazan.** Se mantiene lr 2e-5 con 3 épocas.
  - M2a sube solo +0,007, aunque es más estable entre semillas (desviación 0,010 frente a 0,025).
  - M2b es más inestable (una semilla se queda en 0,552) y sube la FA 8,5 puntos.
- **M2c se rechaza y se mantienen 256 tokens.** Con 512 tokens la FA baja 3 puntos, pero la F1 no sube (−0,005) y el entrenamiento tarda 2,7 veces más (38 min frente a 14 min).

### Paso 3
- **M3b (`usmsc`) se adopta.** Sube +0,049, mejora los 3 pliegues y baja la FA 8,1 puntos. Coincide con lo que se vio en el BiLSTM (+0,06 con B6).
- **M3a (`satira`) se rechaza.** Sobre M3b baja la F1 y sube la FA 4,3 puntos. Solo mejora F2 y empeora claramente F3.
- **M3c (`politica`) se rechaza.** Baja la F1 en los 3 pliegues. Las parejas sintéticas de esta fuente no se transfieren a fuentes nuevas.
- **M4** (cabeza adversarial, opcional) no se ha ejecutado. Para añadirlo hay que acordarlo con Orlando.

## Costo de cada experimento (9 corridas)

| ID | Minutos | Épocas elegidas (9 corridas) | Pico de VRAM |
| --- | --- | --- | --- |
| M0 | 14 | 2, 3, 3, 2, 3, 3, 3, 3, 2 | 3,4 GB |
| M1a | 14 | 3, 3, 2, 2, 3, 2, 3, 2, 1 | 2,3 GB |
| M1c | 18 | 3, 3, 3, 3, 3, 3, 3, 2, 3 | 5,3 GB |
| M2a | 21 | 3, 3, 4, 5, 3, 3, 3, 2, 2 | 2,3 GB |
| M2b | 14 | 3, 2, 2, 3, 3, 3, 1, 2, 2 | 2,3 GB |
| M2c | 38 | 3, 3, 2, 2, 2, 2, 3, 2, 2 | 2,1 GB |
| M3b | 21 | 3, 3, 2, 2, 3, 3, 3, 3, 3 | 2,3 GB |
| M3a | 24 | 2, 3, 2, 3, 2, 3, 2, 2, 3 | 2,3 GB |
| M3c | 25 | 3, 2, 2, 3, 3, 2, 1, 2, 2 | 2,3 GB |

La mediana de épocas del ganador (M3b) es **3**. Es la que usará el modelo final de la fase F (§8).

## Límites

- Las cifras son de validación por fuente dentro del desarrollo. La prueba congelada se evaluará una sola vez, cuando Orlando lo indique.
- F2 (fakedes) sigue siendo el pliegue más difícil para todos los modelos.
- La temperatura todavía no está calibrada. La ajusta Orlando con las predicciones fuera de pliegue de la fase F.
