# Plan de mejora de mBERT (para el responsable de mBERT)

**Fecha:** 7 de noviembre de 2026
**Destinatario:** la persona que entrena mBERT. Este documento se puede seguir sin haber leído el resto, pero conviene leer antes [00_ANALISIS_DATASETS.md](00_ANALISIS_DATASETS.md) (hallazgos de datos) y [01_PLAN_COMUN.md](01_PLAN_COMUN.md) (reglas compartidas).
**Coordinación:** Orlando entrega el conjunto de datos y el evaluador común, y recibe las predicciones y el modelo final. Las preguntas sobre datos o métricas se resuelven con él antes de cambiar nada.

---

## 1. Resumen en una página

**Situación actual.** El checkpoint en uso (`BILSTM_ES_main_len512_seed43_20261008-175737_516f4097`) tiene F1 macro 0,939 en validación y **0,600 en la externa de 569**, con 150 de 307 reales marcadas como falsas. El BiLSTM, con los mismos datos, obtiene 0,603. Un clasificador que solo cuenta palabras obtiene 0,663 en esa misma prueba. **El modelo no está fallando por ser mBERT: los datos y la validación lo están llevando a aprender atajos.**

**Qué cambia:**

1. **Datos:** se entrena con un conjunto común nuevo (`comun_v1`), el mismo que el BiLSTM. Son fragmentos de artículos de 100 a 400 palabras, sin sátira, sin fragmentos truncados de USMSC y sin marcas de medio.
2. **Validación:** se elige con validación cruzada dejando una fuente fuera (3 pliegues), no con las 132 filas actuales.
3. **Modelo base:** se prueban modelos nativos en español (BETO, RoBERTa-BNE) y XLM-R contra mBERT.
4. **Salida:** cada corrida guarda logits por ID. Con ellos Orlando calibra y combina los dos modelos.
5. **Longitud:** se vuelve a comparar 256 contra 512 tokens, ahora con los datos y la validación nuevos (experimento M2c). Tu resultado anterior a favor de 512 es válido para lo que midió, pero se midió con artículos completos en una validación donde la longitud ayuda a acertar (sección 2). 256 entrena unas 2,7 veces más rápido, así que 512 tiene que ganar por la regla para quedarse.

**Qué no se hace:**

- No se modifica `comun_v1` ni se arma otra versión de los datos.
- No se usa la externa de 569, la prueba de 146 ni la validación de 132 para elegir nada.
- No se abre la prueba congelada: sus predicciones se generan solo al final y se entregan a Orlando sin mirarlas.
- No se cambia la convención de etiquetas: sigue `0=REAL, 1=FALSA`.

---

## 2. Por qué cambia el plan: lo que encontramos

Estas cifras salen de los archivos locales y de tus propios informes ([`mBERT/INFORME_TECNICO_ENTRENAMIENTOS_MBERT.md`](../../mBERT/INFORME_TECNICO_ENTRENAMIENTOS_MBERT.md)).

| Hallazgo | Dato | Consecuencia para mBERT |
| --- | --- | --- |
| La validación no predice la externa | 0,939 → 0,600; la semilla 43 ganó en validación y fue la peor en prueba (0,898 frente a 0,936 y 0,934) | Con 132 filas, un error mueve el F1 en 0,008: se estaba eligiendo por ruido |
| Atajo de medio | 98,6 % de las filas con URL vienen de dominios de una sola clase; en Polyglot, el 100 % (todas las reales son de `elmundo.es`) | El modelo aprende a reconocer el medio |
| Atajo de longitud | Las falsas son más cortas (mediana 312 frente a 544 palabras en la externa). Un clasificador de solo longitud saca 0,663 | A 512 tokens, mBERT ve la longitud; la extensión solo envía fragmentos |
| Entrenamiento y validación muy distintos | Mediana de 70 subpalabras en entrenamiento (USMSC) frente a 629 en validación | Se entrenaba con una cosa y se elegía con otra |
| Sátira como «falsa» | La política v4 ya excluyó 233 de sátira del entrenamiento, pero la validación BiLSTM original tenía 36 de 81 falsas de sátira | `comun_v1` la quita de todas las particiones |
| USMSC/Edds residual | 1.647 filas de 36–47 palabras, cortadas a 300 caracteres, sin fuente | Fuera del conjunto principal; solo en un brazo de ablación |
| Probabilidades sin calibrar | Brier externo 0,346, **peor que responder siempre 0,5** (0,25) | Los porcentajes que muestra la extensión no significan lo que dicen |
| Solo se guardan clases | `predictions_validation.jsonl` guarda `pred`, no probabilidades | No se puede calibrar ni combinar |
| mBERT no es nativo en español | Reparte vocabulario entre más de 100 idiomas | BETO o RoBERTa-BNE suelen rendir mejor en español con el mismo tamaño |

---

## 3. Datos que vas a recibir

Orlando entrega la carpeta `datasets/comun_v1/` (no va a Git). Cópiala tal cual en tu equipo, en la misma ruta relativa a la raíz del repositorio.

Usa la versión **`comun_v1.1`** (campo `version` de `manifest.json`): quita 8 artículos de Polyglot que no estaban en español. Si tienes una copia con `comun_v1.0`, reemplázala.

| Archivo | Para qué |
| --- | --- |
| `fragmentos_desarrollo.csv` | Todo el entrenamiento y la validación |
| `fragmentos_prueba_congelada.csv` | **Solo** para generar predicciones al final (sección 8) |
| `ablacion_satira.csv`, `ablacion_usmsc.csv`, `ablacion_politica.csv` | Filas extra de entrenamiento para los brazos de ablación |
| `pliegues.json` | Definición de los 3 pliegues |
| `manifest.json` | SHA-256 de cada archivo y conteos esperados |

Columnas que usa el modelo:

| Columna | Uso |
| --- | --- |
| `id_fragmento` | Identificador; va en las predicciones |
| `id_articulo` | Para agrupar fragmentos de un mismo artículo |
| `grupo` | Para separar la validación interna (sección 5.3) |
| `fuente` | `v1`, `fakedes`, `polyglot` o `falledesinfo` |
| `texto` | **Única entrada del modelo**, como secuencia simple `[CLS] texto [SEP]` |
| `etiqueta_falsa` | Etiqueta: 1 = FALSA, 0 = REAL. Coincide con tu `label` actual: **no hay que invertir nada** |
| `peso` | Peso de la muestra en la pérdida (sección 5.2) |

Columnas que **no** entran al modelo: `dominio`, `tokens_bilstm`, `pliegue`. Son solo para auditoría.

**Pliegues:**

| Pliegue | Entrena con | Evalúa en |
| --- | --- | --- |
| F1 | `fakedes` + `polyglot` | `v1` |
| F2 | `v1` + `polyglot` | `fakedes` |
| F3 | `v1` + `fakedes` | `polyglot` |

---

## 4. Entorno

- Igual que el actual: Python 3.14, PyTorch 2.13.0+cu130, Transformers 5.19.0, Datasets 5.1.0, Accelerate 1.15.0, scikit-learn 1.9.1, RTX 5060 de 8 GB, BF16. No hace falta actualizar nada.
- **Modelos base a descargar** (fijar la revisión exacta del Hub y guardar su SHA-256, como ya haces con mBERT):

| Clave | ID en Hugging Face | Parámetros | Notas |
| --- | --- | --- | --- |
| `mbert` | `google-bert/bert-base-multilingual-cased` | ~178 M | Ya lo tienes, revisión `3f076fdb…` |
| `beto` | `dccuchile/bert-base-spanish-wwm-cased` | ~110 M | BERT español, *cased* |
| `roberta_bne` | `PlanTL-GOB-ES/roberta-base-bne` (puede figurar como `BSC-LT/roberta-base-bne`) | ~125 M | RoBERTa entrenado con el corpus de la Biblioteca Nacional; verifica el nombre vigente |
| `xlmr` | `FacebookAI/xlm-roberta-base` | ~278 M | Multilingüe, más fuerte que mBERT; el más lento de los cuatro |

- **Tokenizadores:** cada modelo usa el suyo. El aviso de la expresión regular de Mistral solo aplicaba al tokenizador BERT; con cualquier otro, no actives `fix_mistral_regex` sin comprobar primero que no cambia los IDs.
- **Disco:** la matriz anterior llenó la unidad D: con checkpoints por época y estado del optimizador. Usa `save_only_model=True` y `save_total_limit=1`, y conserva solo `best_model` de cada corrida.

---

## 5. Cambios en el script de entrenamiento

Crea un script nuevo, `mBERT/train_comun.py`, a partir de [`mBERT/train_bilstm_step4.py`](../../mBERT/train_bilstm_step4.py). **No modifiques el antiguo:** tiene que seguir reproduciendo los resultados de octubre. Mantén todo lo que ya hace bien: hashes, una carpeta por corrida con `exist_ok=False`, recarga explícita del mejor checkpoint y comprobación de la métrica.

### 5.1. Lista de cambios

| # | Antes (`train_bilstm_step4.py`) | Después (`train_comun.py`) |
| --- | --- | --- |
| 1 | `DATA = datasets/processed/mbert_bilstm_step3_20261008_v1`, JSONL | `datasets/comun_v1/fragmentos_desarrollo.csv`; verificar SHA-256 y conteos contra `manifest.json` |
| 2 | `--arm main\|no_usmsc` | `--pliegue F1\|F2\|F3\|todo` y `--ablacion ninguna\|satira\|usmsc\|politica` |
| 3 | `MODEL` fijo en mBERT | `--modelo mbert\|beto\|roberta_bne\|xlmr`, con ruta local, revisión y SHA-256 por modelo en un diccionario |
| 4 | `LENGTHS = (128,192,256,512)` | `--max-length` libre; valor por defecto 256 |
| 5 | `SEEDS = (42,43,44)` y `assert args.epochs == 3` | `--seed` y `--epochs` libres; sin `assert` |
| 6 | `learning_rate=2e-5` fijo | `--lr`, por defecto 2e-5 |
| 7 | Pérdida sin pesos | Pérdida ponderada con la columna `peso` (sección 5.2) |
| 8 | Elegir época con la validación de 132 | Elegir época con una **validación interna** del 10 % de los grupos del entrenamiento del pliegue (sección 5.3) |
| 9 | `predictions_validation.jsonl` con `pred` | `predicciones.csv` con **logits** de la fuente que quedó fuera, en el formato común (sección 5.4) |
| 10 | `save_total_limit=None` | `save_only_model=True`, `save_total_limit=1` |
| 11 | Métricas propias en `score()` | Mantener `score()` para el registro, pero las métricas oficiales las calcula el evaluador común a partir de `predicciones.csv` |

### 5.2. Pérdida ponderada

`Trainer` no usa pesos por muestra. Basta con una subclase:

```python
class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        weights = inputs.pop("peso")
        labels = inputs.get("labels")
        outputs = model(**inputs)
        loss = torch.nn.functional.cross_entropy(outputs.logits, labels, reduction="none")
        loss = (loss * weights).sum() / weights.sum()
        return (loss, outputs) if return_outputs else loss
```

Para que `peso` llegue al lote:

- Incluye `peso` en el `Dataset`.
- Usa `remove_unused_columns=False` en `TrainingArguments`.
- Asegúrate de que el `DataCollatorWithPadding` lo deja pasar como tensor `float`.

**Comprobación:** en la primera corrida, registra en el log la suma de pesos por clase del entrenamiento. Debe estar cerca de 1:1 o, al menos, mucho más equilibrada que 1.756/1.032.

### 5.3. Validación interna para elegir la época

- Dentro del entrenamiento de cada pliegue, separa el 10 % de los **grupos** (no de las filas) con `GroupShuffleSplit(test_size=0.1, random_state=semilla)`, estratificando por fuente si es posible.
- Entrena con el 90 % y evalúa cada época en ese 10 %. Elige la época por F1 macro, con empate a favor de la época anterior, como ya haces.
- **La fuente que quedó fuera no se usa para elegir la época.** Solo se predice con el mejor checkpoint al terminar.

### 5.4. Predicciones de salida

Con el mejor checkpoint, predice **todos los fragmentos de la fuente que quedó fuera** y escribe `predicciones.csv` en la carpeta de la corrida:

```python
logits = trainer.predict(test_ds).predictions          # forma (n, 2)
prob = torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1)[:, 1]
pd.DataFrame({
    "id_fragmento": ids,
    "modelo": args.modelo,
    "configuracion": nombre_config,      # p. ej. "beto_len256_lr2e-5_ep3"
    "semilla": args.seed,
    "pliegue": args.pliegue,
    "logit_real": logits[:, 0],
    "logit_falsa": logits[:, 1],
    "prob_falsa": prob.numpy(),
}).to_csv(out / "predicciones.csv", index=False)
```

- Los logits se guardan en `float32`, aunque el modelo corra en BF16.
- Escribe también `config.json` (todos los argumentos, revisión y SHA-256 del modelo base, SHA-256 de `comun_v1`, SHA-256 del script) y `metricas_internas.json` (las de la validación interna por época).

### 5.5. Ejecutor de la matriz

Adapta [`mBERT/run_bilstm_step4_matrix.py`](../../mBERT/run_bilstm_step4_matrix.py) a `run_comun_matrix.py`. Recibe una configuración y lanza los 3 pliegues × 3 semillas, en serie, con un registro de estado como `PASO_4_MATRIX_STATUS.json`. Si una corrida falla, el ejecutor se detiene y no la repite en silencio.

---

## 6. Experimentos, en orden

Cada experimento es **una configuración × 3 pliegues × 3 semillas = 9 corridas**. Tiempo estimado por corrida a 256 tokens con unos 2.900 fragmentos de entrenamiento: unos 3 minutos con mBERT o BETO (tu `main/256` tardó 163 s con 2.788 filas) y unos 6 minutos con XLM-R. Unos **30 minutos por experimento**, una hora con XLM-R.

**Regla para adoptar un cambio** (fijada antes de entrenar, la misma que el BiLSTM): la media de F1 macro de artículo en los 3 pliegues debe subir **al menos 0,02** y la tasa de falsas alarmas no debe subir más de 2 puntos. Si la diferencia es menor, gana la opción más barata. Las métricas las calcula el evaluador común de Orlando con tus `predicciones.csv`.

**Cambia una sola cosa por experimento** respecto al ganador anterior.

| Paso | ID | Configuración | Pregunta |
| --- | --- | --- | --- |
| 0 | **M0** | `mbert`, 256 tokens, lr 2e-5, 3 épocas, decaimiento 0,01, calentamiento 10 %, lote efectivo 16, BF16, pesos por muestra | ¿Cuánto rinde la receta actual con los datos y la validación nuevos? |
| 0 | **M0-len** | Comprobación, no experimento: % de fragmentos truncados a 256 con cada tokenizador | Registrar el dato. Los fragmentos de hasta 400 palabras pasarán de 256 subpalabras; es esperado y es lo que mide M2c |
| 1 | **M1a** | `beto`, resto igual que M0 | ¿Un BERT español supera a mBERT? |
| 1 | **M1b** | `roberta_bne`, resto igual que M0 | ¿Y un RoBERTa español? |
| 1 | **M1c** | `xlmr`, resto igual que M0 | ¿Y un multilingüe más fuerte? |
| 2 | **M2a** | Ganador del paso 1 con lr 1e-5 y hasta 5 épocas | ¿Aprende mejor más despacio? |
| 2 | **M2b** | Ganador del paso 1 con lr 3e-5 y hasta 3 épocas | ¿O más rápido? |
| 2 | **M2c** | Ganador de M2a/M2b con 512 tokens (microlote 2, acumulación 8, *gradient checkpointing*, como ya hacías) | ¿Leer más del fragmento ayuda con la validación por fuente? |
| 3 | **M3a** | Ganador + brazo `satira` | ¿La sátira ayuda o confunde? |
| 3 | **M3b** | Ganador + brazo `usmsc` | ¿Los fragmentos USMSC aportan algo medido por fuente? |
| 3 | **M3c** | Ganador + brazo `politica` | ¿Las parejas sintéticas enseñan algo transferible? |
| 4 | **M4** (opcional) | Ganador + cabeza adversarial de fuente (sección 6.1) | ¿Quitar la información de medio de la representación mejora la generalización? |

Notas sobre el orden:

- **En el paso 1, los tres modelos compiten contra M0** y entre ellos. Si dos quedan a menos de 0,02, gana el más pequeño y rápido (BETO > RoBERTa-BNE > mBERT > XLM-R).
- **En el paso 2,** M2a y M2b compiten contra el ganador del paso 1 y entre ellos. Después, M2c compara la longitud sobre el ganador. Si 512 no gana por 0,02, se queda 256 por ser más rápido.
- **En el paso 3,** cada brazo se compara solo contra el ganador del paso 2. Un brazo se adopta si además mejora en al menos 2 de los 3 pliegues.
- **No añadas experimentos a la lista** sin acordarlo antes con Orlando. Cada experimento extra aumenta la probabilidad de ganar por azar.

### 6.1. Cabeza adversarial de fuente (opcional, M4)

Solo si los pasos 1–3 terminaron y queda tiempo.

- Añade al modelo una segunda cabeza lineal que predice la `fuente` a partir del mismo vector `[CLS]`, con una **capa de inversión de gradiente** entre el vector y esa cabeza.
- Pérdida total = pérdida de clase + λ × pérdida de fuente, con λ = 0,1 fijo (no se ajusta).
- En cada pliegue solo hay 2 fuentes en entrenamiento, así que la cabeza de fuente es binaria.
- En inferencia, la cabeza de fuente se descarta. El contrato y el backend no cambian.

```python
class GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lam):
        ctx.lam = lam
        return x.view_as(x)
    @staticmethod
    def backward(ctx, grad):
        return -ctx.lam * grad, None
```

---

## 7. Modelo final

Cuando el paso 3 (o el 4) termine:

1. **Entrena la configuración ganadora con todo el desarrollo** (`--pliegue todo`), con 3 semillas. Número de épocas: la mediana de las épocas elegidas en los 9 entrenamientos por pliegue. Sin validación interna en esta corrida.
2. **Conjunto de semillas:** Orlando decide, con las predicciones fuera de pliegue, si promediar los logits de las 3 semillas compensa triplicar el tiempo de inferencia (umbral: +0,01 de F1). Entrega las 3 por si acaso.
3. **No calibres tú.** Orlando ajusta la temperatura con las predicciones fuera de pliegue de todos los modelos a la vez, para que la calibración y la combinación sean coherentes. Te devuelve el valor de `T` para el contrato.

---

## 8. Prueba congelada

Solo cuando Orlando lo indique, con el modelo final ya fijado:

1. Predice `fragmentos_prueba_congelada.csv` con el modelo final (y con las 3 semillas si se entregan).
2. Guarda `predicciones_congelada.csv` con el mismo formato que la sección 5.4 y `pliegue = "congelada"`.
3. **Entrégalo sin calcular métricas.** El evaluador común lo hace una sola vez para los dos modelos.

---

## 9. Entregables

| Entregable | Contenido |
| --- | --- |
| `mBERT/train_comun.py` y `mBERT/run_comun_matrix.py` | Scripts nuevos, con los cambios de la sección 5 |
| `mBERT/runs_comun/<corrida>/` por cada corrida | `config.json`, `metricas_internas.json`, `predicciones.csv`, `train_log.jsonl`. Para las corridas de pliegue, el `best_model` se puede borrar una vez entregadas las predicciones |
| `mBERT/runs_comun/FINAL_<modelo>_s<semilla>/best_model` | Pesos finales y tokenizador (Git LFS) |
| `mBERT/selection/comun_v1/contrato_inferencia.json` | Contrato nuevo (sección 10) |
| `mBERT/PLAN_COMUN_RESULTADOS.md` | Tabla por experimento: configuración, decisión y motivo; problemas encontrados |
| `predicciones_congelada.csv` | Solo al final |

---

## 10. Contrato de inferencia nuevo

El backend ([`backend/models/mbert.py`](../../backend/models/mbert.py)) lee hoy `mBERT/selection/bilstm_step5_20261008_v1/selection.json` y **exige `max_length == 512`** y el tokenizador mBERT (línea 36). Con un modelo nuevo esa comprobación falla, así que Orlando actualizará el backend para leer este contrato:

```json
{
  "estado": "congelado",
  "modelo_base": {"clave": "beto", "hub_id": "dccuchile/bert-base-spanish-wwm-cased", "revision": "…", "sha256": "…"},
  "conjunto": {"nombre": "comun_v1", "sha256_manifest": "…"},
  "checkpoints": [
    {"ruta": "mBERT/runs_comun/FINAL_beto_s42/best_model", "sha256_model": "…", "semilla": 42}
  ],
  "tokenizador": {"ruta": "mBERT/runs_comun/FINAL_beto_s42/best_model", "sha256_tokenizer_json": "…"},
  "entrada": "texto_unico",
  "max_length": 256,
  "label2id": {"REAL": 0, "FALSA": 1},
  "temperatura": 1.0,
  "umbral_falsa": 0.5,
  "combinar_semillas": "media_logits"
}
```

- Si el backend usa varias semillas, `checkpoints` tiene 3 entradas.
- `temperatura` la rellena Orlando tras la calibración.
- Mantén los campos de hash: el backend los verifica antes de cargar.
- Actualiza [`mBERT/inferir_bilstm_mbert.py`](../../mBERT/inferir_bilstm_mbert.py) para que lea este contrato, o crea `inferir_comun.py`, con `softmax(logits / temperatura)`.

---

## 11. Lista de comprobación

- [ ] `comun_v1` recibido y verificado contra su `manifest.json`.
- [ ] Modelos base descargados, con revisión y SHA-256 registrados.
- [ ] `train_comun.py` con los 11 cambios de la sección 5.1.
- [ ] Prueba corta (1 época, un pliegue) que genera `predicciones.csv` válido y muestra pesos por clase equilibrados.
- [ ] M0 y comprobación M0-len.
- [ ] Paso 1 (M1a–M1c) y decisión anotada.
- [ ] Paso 2 (M2a–M2c) y decisión anotada, incluida la longitud.
- [ ] Paso 3 (M3a–M3c) y decisión anotada.
- [ ] (Opcional) M4.
- [ ] Modelo final con 3 semillas.
- [ ] Contrato de inferencia con hashes; `temperatura` recibida de Orlando.
- [ ] Predicciones de la prueba congelada entregadas sin mirar métricas.
- [ ] `PLAN_COMUN_RESULTADOS.md` completo.

## 12. Preguntas frecuentes

**¿Por qué no seguir con 512 tokens si ganaba en validación?**
No se descarta: se vuelve a medir en M2c. Pero el resultado anterior tiene tres límites:

- `main/512` ganó a `main/256` por **0,0103** (0,9220 frente a 0,9117) en 132 filas, apenas por encima del margen de empate de 0,01 que tú mismo fijaste. Son uno o dos ejemplos.
- La validación eran artículos completos (mediana de 629 subpalabras) en los que las falsas son más cortas. A 512 el modelo ve más de esa diferencia de longitud, y con solo contar palabras se obtiene 0,663 en la externa.
- En la externa, el modelo de 512 rindió 0,718 en textos de menos de 200 palabras y 0,414 en los de 1.000 o más. Leer más no le ayudó en los textos largos.

Al BiLSTM le pasó lo mismo: 512 tokens ganó en su validación (0,693 frente a 0,646 con 192), pero en la externa los mejores modelos fueron los de 192.

**¿Por qué quitar USMSC si subía la validación?**
Subía una validación de 132 filas de dos fuentes. Ahora se mide como brazo de ablación (M3b) con validación por fuente. Si ayuda de verdad, se adopta.

**¿Y si ningún modelo nuevo supera a mBERT por 0,02?**
Se queda mBERT con la receta M0. La mejora viene entonces de los datos nuevos, de la calibración y de la combinación con el BiLSTM. Es un resultado válido.

**¿Puedo mirar la externa de 569 para ver cómo voy?**
No para decidir nada. Ya se consultó muchas veces y premia la longitud del artículo. La referencia ahora son los 3 pliegues.

**¿Qué pasa con el pliegue F3 (Polyglot)?**
Ahí las reales son todas de El Mundo y las falsas de medios de propaganda, así que es fácil acertar por el medio. Se informa, pero no decide solo: la regla usa la media de los tres pliegues y, para los brazos de ablación, exige mejora en al menos dos.
