# Plan de mejora del BiLSTM

**Fecha:** 7 de noviembre de 2026
**Responsable:** Orlando.
**Requisito previo:** el conjunto común `comun_v1` y el evaluador común de [01_PLAN_COMUN.md](01_PLAN_COMUN.md).

## 1. Punto de partida

| Dato | Valor actual |
| --- | --- |
| Checkpoint en producción | `datasets/modelos_balanceados/pequeno_mejorado_fasttext_cc300_s42/mejor_modelo.pt` |
| Script | [`bilstm/preentrenados/entrenar.py`](../../bilstm/preentrenados/entrenar.py) |
| Arquitectura | Embedding fastText CC 300 d (ajustable) → BiLSTM 1 capa, 64 por dirección → estado final de ambas direcciones → lineal |
| Entrada | Hasta 192 tokens de `\b\w+\b` en minúsculas ([`entrenar_baseline.py:29`](../../bilstm/entrenar_baseline.py:29)) |
| Entrenamiento | AdamW lr 1e-3, decaimiento 0,01, lote 32, dropout 0,3, pérdida ponderada por clase, ReduceLROnPlateau, parada temprana con paciencia 5 por F1 macro de validación |
| Etiqueta | `0=falsa`, `1=real` |
| Datos | 3.066 filas: 1.683 USMSC/Edds truncados, 769 v1 (con 233 de sátira), 614 Polyglot |
| Resultados | Validación 0,765 · prueba 0,774 · externa 0,603 (164/307 falsas alarmas) |
| Backend | Umbral fijo 0,5 en [`backend/models/bilstm.py:97`](../../backend/models/bilstm.py:97), sin calibración |

Problemas propios del BiLSTM, además de los comunes:

- **Más de la mitad del entrenamiento (1.683 filas) son fragmentos de 43 palabras sin procedencia,** mientras que la extensión envía 100 tokens o más.
- **El 44 % de las falsas de validación son sátira.** La validación premiaba detectar sátira.
- **Solo usa el estado final** para representar el texto: en 192 tokens, lo del principio se diluye.
- **Los embeddings se ajustan desde la primera época** con pocos miles de textos, lo que favorece el sobreajuste.

## 2. Cambios de código necesarios (antes de experimentar)

Hacer en un script nuevo, `bilstm/entrenar_comun.py`, para no romper la reproducción de los modelos anteriores:

1. **Lectura del conjunto común:** leer `datasets/comun_v1/fragmentos_desarrollo.csv`, verificar el SHA-256 contra `manifest.json` y filtrar por pliegue (`--pliegue F1|F2|F3`).
2. **Convención de etiquetas:** usar `etiqueta_falsa` (1 = falsa). Dentro del modelo, la neurona 1 pasa a ser «falsa». Cambiar en consecuencia [`probar_externo.py`](../../bilstm/probar_externo.py) y el backend (paso 5).
3. **Pesos por muestra:** usar la columna `peso` en la pérdida (`CrossEntropyLoss(reduction="none")` × `peso`), además o en lugar del peso por clase. Probar ambas opciones solo si la primera no equilibra la tasa de falsas alarmas.
4. **Parada temprana interna:** separar el 10 % de los grupos del entrenamiento del pliegue como validación interna. La fuente que quedó fuera no se usa para elegir la época.
5. **Guardar predicciones** en el formato común de [01_PLAN_COMUN.md §7](01_PLAN_COMUN.md#7-formato-común-de-predicciones), con logits, para la fuente que quedó fuera.
6. **Parámetros por línea de comandos:** pooling, congelación de embeddings, máximo de tokens y brazo de ablación, para que cada experimento sea una línea de comando y no una copia del script.
7. **Guardar en cada carpeta** `config.json`, el hash del conjunto, el hash del script y `predicciones.csv`.

## 3. Experimentos, en orden

Cada experimento son **3 pliegues × 3 semillas = 9 corridas**. Cada uno cambia **una sola cosa** respecto al ganador anterior y se decide con las reglas de [01_PLAN_COMUN.md §6](01_PLAN_COMUN.md#6-reglas-de-decisión-fijadas-antes-de-entrenar): adoptar solo si la media de F1 macro de artículo sube al menos 0,02 sin subir las falsas alarmas más de 2 puntos.

| ID | Cambio | Hipótesis | Coste |
| --- | --- | --- | --- |
| **B0** | Receta actual sin cambios, con `comun_v1` | Línea base honesta en el nuevo protocolo | 9 corridas cortas |
| **B1** | Pooling: concatenar max + media de todas las salidas (en lugar del estado final) | Usa todo el fragmento, no solo los extremos | Igual |
| **B2** | Pooling con atención aditiva simple | Igual que B1, pesando las palabras útiles | Igual |
| **B3** | Embeddings congelados las primeras 3 épocas y liberados después con lr × 0,1 | Menos sobreajuste con pocos datos | Igual |
| **B4** | Tamaño oculto 128 (en vez de 64) | Más capacidad ahora que hay más fragmentos | Algo más lento |
| **B5** | Brazo `+satira` | Ver [01_PLAN_COMUN.md §3.6](01_PLAN_COMUN.md#36-brazos-de-ablación) | Igual |
| **B6** | Brazo `+usmsc` | Igual | Igual |
| **B7** | Brazo `+politica` | Igual | Igual |
| **B8** | Máximo de 320 tokens (en vez de 192) | En la validación anterior, 512 ganó a 192 (0,693 frente a 0,646), pero en la externa ganaron los de 192. Se mide de nuevo con la validación por fuente | Algo más lento |

Notas:

- **B1 y B2 compiten entre sí:** se prueba B2 solo si B1 se adopta, y gana el mejor de los dos.
- **Máximo de tokens:** se parte de 192, el valor actual del backend. Los fragmentos van de 100 a 400 tokens, así que los más largos se recortan, igual que en producción. B8 mide si leer más ayuda.
- **Opcional, no prioritario:** dar vector a las palabras fuera del vocabulario con los subword de fastText. Requiere descargar `cc.es.300.bin` (unos 7 GB) porque en `datasets/embeddings_preentrenados/` solo está el `.vec`. Probarlo solo si el análisis de errores muestra muchas palabras desconocidas.
- **Sin hiperparámetros nuevos fuera de esta lista.** Si B0–B7 no mejoran, el BiLSTM se queda con la receta B0 y la mejora viene de la calibración.

## 4. Comparación con la referencia TF-IDF

Con el evaluador común, comparar la configuración ganadora contra **TF-IDF de caracteres 3–5 + regresión logística** en los mismos pliegues.

- **Si el BiLSTM supera al TF-IDF** en 0,02 o más: se mantiene el BiLSTM.
- **Si empatan o pierde:** decisión de Orlando. El TF-IDF calibrado es más rápido, más pequeño y más fácil de explicar, y podría ocupar el lugar del BiLSTM en el backend con el mismo contrato (`probabilidad_falsa`).

## 5. Entrega final y cambios en el backend

1. **Modelo final:** entrenar la configuración ganadora con **todo el desarrollo** (los tres pliegues juntos), 3 semillas, usando como número de épocas la mediana de las épocas elegidas en los pliegues.
2. **Semillas:** promediar los logits de las 3 semillas si la ganancia fuera de pliegue es de 0,01 o más. Si no, usar una sola y ahorrar inferencia.
3. **Calibración:** guardar la temperatura `T` ajustada con las predicciones fuera de pliegue ([01_PLAN_COMUN.md §5](01_PLAN_COMUN.md#5-calibración-umbral-y-combinación)).
4. **Contrato de inferencia** dentro del checkpoint o en un `contrato.json` junto a él:

   ```json
   {
     "modelo": "bilstm",
     "version": "comun_v1_<config>_<fecha>",
     "etiquetas": {"real": 0, "falsa": 1},
     "max_tokens": 192,
     "temperatura": 1.0,
     "umbral_falsa": 0.5,
     "sha256_checkpoint": "…",
     "sha256_conjunto": "…"
   }
   ```

5. **Backend:**
   - [`backend/models/bilstm.py`](../../backend/models/bilstm.py): leer el contrato, aplicar `softmax(logits / T)` y tomar la probabilidad de la neurona «falsa» según `etiquetas`. Quitar el 0,5 fijo de la línea 97 y usar `umbral_falsa`.
   - Ajustar los tests de `backend/tests` que dependan del orden de etiquetas.
   - Actualizar `GET /metricas` con las métricas nuevas (fuera de pliegue y prueba congelada).

## 6. Lista de comprobación

- [ ] `comun_v1` construido y con manifiesto revisado.
- [ ] `entrenar_comun.py` con los cambios de la sección 2 y sus tests.
- [ ] B0 ejecutado y comparado con las referencias de longitud y TF-IDF.
- [ ] B1–B7 ejecutados en orden, con la decisión anotada en una tabla de registro.
- [ ] Modelo final, temperatura y contrato guardados.
- [ ] Backend actualizado y probado con la extensión.
- [ ] Predicciones sobre la prueba congelada entregadas al evaluador común **una sola vez**.
