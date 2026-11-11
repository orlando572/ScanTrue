# Plan de mejora de mBERT (para el responsable de mBERT)

**Fecha:** 7 de noviembre de 2026 · **Actualizado:** 10 de noviembre de 2026 (rama `develop`, orden y limpieza, alineación con el BiLSTM B6)
**Destinatario:** la persona que entrena mBERT. Se puede seguir sin leer el resto, pero conviene leer antes [00_ANALISIS_DATASETS.md](00_ANALISIS_DATASETS.md) (hallazgos de datos) y [01_PLAN_COMUN.md](01_PLAN_COMUN.md) (reglas compartidas).
**Coordinación:** Orlando entrega el conjunto común y el código común, y recibe las predicciones y el modelo final. Las preguntas sobre datos o métricas se resuelven con él antes de cambiar nada.

**Orden de trabajo:**

| Fase | Sección | Qué haces | Resultado |
| --- | --- | --- | --- |
| A | [3](#3-preparar-la-rama-y-el-entorno) | Traer `develop` a tu rama, instalar Git LFS, preparar el entorno | Rama `mbert` al día con `develop` |
| B | [4](#4-datos-que-recibes-y-dónde-van) | Recibir y verificar `comun_v1` | `datasets/comun_v1/` verificado |
| C | [5](#5-ordenar-y-limpiar-antes-de-entrenar) | Guardar lo actual en un commit, ordenar `mBERT/` y tus datos | Carpeta limpia; la app sigue funcionando |
| D | [6](#6-script-único-de-entrenamiento) | Crear `mBERT/entrenar.py` | Una corrida corta que funciona |
| E | [7](#7-experimentos-en-orden) | Experimentos M0 → M3 | Configuración ganadora |
| F | [8](#8-modelo-final) y [9](#9-contrato-de-inferencia) | Modelo final y contrato | `final/` con su `contrato.json` |
| G | [10](#10-entrega-y-unión-con-develop) | Entregar a Orlando y unir con `develop` | PR `mbert` → `develop` |
| H | [11](#11-prueba-congelada) | Prueba congelada, cuando Orlando lo indique | `predicciones_congelada.csv` |

Si trabajas con un asistente de IA (Claude Code, Codex, Cursor…), dale la instrucción de la [sección 14](#14-instrucción-para-tu-asistente-de-ia) para que siga este plan fase por fase.

---

## 1. Resumen en una página

**Situación actual.** El checkpoint en uso (`BILSTM_ES_main_len512_seed43_20261008-175737_516f4097`) tiene F1 macro 0,939 en validación y **0,600 en la externa de 569**, con 150 de 307 reales marcadas como falsas. El BiLSTM, con los mismos datos, obtenía 0,603. Un clasificador que solo cuenta palabras obtiene 0,663 en esa misma prueba. **El modelo no está fallando por ser mBERT: los datos y la validación lo llevaban a aprender atajos.**

**Qué cambia:**

1. **Datos:** se entrena con el conjunto común `comun_v1` (versión 1.1), **el mismo con el que se entrenó el BiLSTM B6**. Son fragmentos de artículos de 100 a 400 palabras, sin sátira, sin marcas de medio y solo en español.
2. **Validación:** se elige con validación cruzada dejando una fuente fuera (3 pliegues), no con las 132 filas actuales.
3. **Modelo base:** se prueban modelos en español (BETO y MarIA) y XLM-R contra mBERT. Solo uno llega a la app.
4. **Salida:** cada corrida guarda logits por fragmento, en el mismo formato que el BiLSTM. Con ellos Orlando calibra y combina los dos modelos.
5. **Longitud:** se vuelve a comparar 256 contra 512 tokens con los datos y la validación nuevos (M2c).
6. **Orden:** como en el BiLSTM, un solo script de entrenamiento, carpetas ordenadas y nada que ya no se use.

**Qué no se hace:**

- No se modifica `comun_v1` ni se arma otra versión de los datos.
- No se usa la externa de 569, la prueba de 146 ni la validación de 132 para elegir nada.
- No se abre la prueba congelada: sus predicciones se generan solo al final y se entregan sin mirarlas.
- No se cambia la convención de etiquetas: **1 = falsa, 0 = real**, igual que tu `label` actual y que el BiLSTM B6.
- No se toca la rama `main`.

**Lo que es común no limita tu modelo.** Con el BiLSTM se comparte solo **cómo se mide y cómo se entrega**, no cómo se construye el modelo. El objetivo es que tu modelo **supere al BiLSTM B6** (F1 0,585):

| Común con el BiLSTM (no se cambia) | Libre para ti (para mejorar) |
| --- | --- |
| Datos `comun_v1.1`, pliegues y validación interna | Modelo base: mBERT, BETO, MarIA o XLM-R |
| Métricas, evaluador común y regla de decisión | Longitud: 256 o 512 tokens (no estás atado a los 192 del BiLSTM) |
| Etiquetas: 1 = falsa, 0 = real | Learning rate, épocas, lote, calentamiento |
| Formato de `predicciones.csv` y del contrato | Brazos de ablación (USMSC, sátira, política) |
| Estructura de carpetas | Cabeza adversarial de fuente (M4) y otras ideas que acuerdes con Orlando |

Lo común existe para que los dos modelos se puedan comparar con la misma vara y combinarse en la app. Nada de lo que decidió el BiLSTM te obliga: que USMSC le ayudara es una pista, no una regla. Se espera que un modelo preentrenado en español generalice mejor que el BiLSTM a fuentes que no vio; si con estos datos no lo supera, también es un resultado válido.

---

## 2. Por qué cambia el plan: lo que encontramos

Estas cifras salen de los archivos locales y de tus propios informes ([`mBERT/INFORME_TECNICO_ENTRENAMIENTOS_MBERT.md`](../../mBERT/INFORME_TECNICO_ENTRENAMIENTOS_MBERT.md)).

| Hallazgo | Dato | Consecuencia para mBERT |
| --- | --- | --- |
| La validación no predice la externa | 0,939 → 0,600; la semilla 43 ganó en validación y fue la peor en prueba (0,898 frente a 0,936 y 0,934) | Con 132 filas, un error mueve el F1 en 0,008: se estaba eligiendo por ruido |
| Atajo de medio | 98,6 % de las filas con URL vienen de dominios de una sola clase; en Polyglot, el 100 % (todas las reales son de `elmundo.es`) | El modelo aprende a reconocer el medio |
| Atajo de longitud | Las falsas son más cortas (mediana 312 frente a 544 palabras en la externa). Un clasificador de solo longitud saca 0,663 | A 512 tokens, mBERT ve la longitud; la extensión solo envía fragmentos |
| Entrenamiento y validación muy distintos | Mediana de 70 subpalabras en entrenamiento (USMSC) frente a 629 en validación | Se entrenaba con una cosa y se elegía con otra |
| Sátira como «falsa» | La validación original tenía 36 de 81 falsas de sátira | `comun_v1` la quita de todas las particiones |
| Textos que no están en español | 8 falsas de Polyglot en inglés, francés o italiano | `comun_v1.1` las quita |
| Probabilidades sin calibrar | Brier externo 0,346, **peor que responder siempre 0,5** (0,25) | Los porcentajes que muestra la extensión no significan lo que dicen |
| Solo se guardan clases | `predictions_validation.jsonl` guarda `pred`, no probabilidades | No se puede calibrar ni combinar |
| mBERT no es nativo en español | Reparte vocabulario entre más de 100 idiomas | BETO o MarIA suelen rendir mejor en español con menos parámetros |

**Lo que aprendimos con el BiLSTM** (detalle en [`bilstm/docs/RESULTADOS_MODELO_NUEVO.md`](../../bilstm/docs/RESULTADOS_MODELO_NUEVO.md)):

- **Con fuentes nunca vistas, las cifras son modestas:** el BiLSTM B6 saca F1 0,585 (TF-IDF 0,554, solo longitud 0,533). No compares con el 0,939 de antes: se mide otra cosa.
- **Lo único que ayudó al BiLSTM fue añadir USMSC** (brazo `usmsc`, +0,06). Pooling, congelar embeddings, más neuronas o 320 tokens no ayudaron. Por eso M3b es importante.
- **Una sola semilla no basta para decidir:** la receta base del BiLSTM se movió 0,03 al quitar 8 artículos, más que el umbral de 0,02.
- **Si te apartas de la regla de decisión, anótalo:** el BiLSTM eligió B6 a mano y el motivo quedó en su `contrato.json` (campo `eleccion`). Haz lo mismo.

---

## 3. Preparar la rama y el entorno

### 3.1. Ramas de Git

```
main  ← solo recibe develop cuando todo está completo y probado (no se toca)
  └── develop  ← aquí se unen bilstm, mbert, backend y frontend
        ├── bilstm  (Orlando)
        └── mbert   (tú)
```

1. **Trae `develop` a tu rama antes de empezar.** `develop` ya tiene el BiLSTM nuevo, el código común (`datos_comunes/`), el backend adaptado y la documentación. Desde tu copia del repositorio:
   ```bash
   git fetch origin
   git switch mbert
   git merge origin/develop
   ```
   Si no tienes la rama `mbert` en local, créala desde la remota (`git switch -c mbert origin/mbert`) y haz el `merge`. Si hay conflictos, resuélvelos conservando lo de `develop` en todo lo que no sea `mBERT/`.
2. **Trabaja siempre en `mbert`.** Cuando termines cada fase importante, súbela (`git push origin mbert`).
3. **Nunca hagas commit ni merge en `main`.** Al final abres una PR de `mbert` hacia `develop` (sección 10).
4. **Git LFS es obligatorio:** los pesos de mBERT van con LFS (ver `.gitattributes`). Instálalo y actívalo una vez (`git lfs install`). Sin LFS, los pesos llegan como archivos de texto de 3 líneas y la app no carga mBERT.

### 3.2. Entorno

- Igual que el actual: Python 3.14, PyTorch 2.13.0+cu130, Transformers 5.19.0, Datasets 5.1.0, Accelerate 1.15.0, scikit-learn 1.9.1, RTX 5060 de 8 GB, BF16. `datos_comunes/` solo necesita además `pandas` y `numpy`.
- **Modelos base** (fija la revisión exacta del Hub y guarda su SHA-256, como ya haces con mBERT):

| Clave | ID en Hugging Face | Parámetros | Notas |
| --- | --- | --- | --- |
| `mbert` | `google-bert/bert-base-multilingual-cased` | ~178 M | Ya lo tienes, revisión `3f076fdb…` |
| `beto` | `dccuchile/bert-base-spanish-wwm-cased` | ~110 M | BERT en español, *cased* |
| `roberta_bne` | `PlanTL-GOB-ES/roberta-base-bne` (puede figurar como `BSC-LT/roberta-base-bne`) | ~125 M | **MarIA**: RoBERTa entrenado con el corpus de la Biblioteca Nacional. Verifica el nombre vigente |
| `xlmr` | `FacebookAI/xlm-roberta-base` | ~278 M | Multilingüe, más fuerte que mBERT; el más lento |

- **Tokenizadores:** cada modelo usa el suyo. El aviso de la expresión regular de Mistral solo aplicaba al tokenizador BERT; con cualquier otro, no actives `fix_mistral_regex` sin comprobar que no cambia los IDs.
- **Disco:** la matriz anterior llenó la unidad D: con checkpoints por época. Usa `save_only_model=True` y `save_total_limit=1`, y borra el `best_model` de cada corrida de experimento en cuanto tenga su `predicciones.csv`.
- **Hardware:** BETO y MarIA caben en la RTX 5060 igual que mBERT. También en una RTX 3050 de 6 GB a 256 tokens (BF16, microlote 8); a 512, con microlote 2, acumulación 8 y *gradient checkpointing*, más lento. Las versiones *large* no son viables en estas GPU.

---

## 4. Datos que recibes y dónde van

### 4.1. El conjunto común

**No está en GitHub** (el repositorio es público y contiene textos de terceros). Orlando te lo pasa en un zip `comun_v1.1.zip` con su SHA-256.

1. Descomprímelo en `datasets/comun_v1/`, en la raíz del repositorio.
2. Comprueba que `manifest.json` dice `"version": "comun_v1.1"`. Si tenías una copia `comun_v1.0`, bórrala.
3. **Verifica los fragmentos, no el manifiesto:** el SHA-256 de `fragmentos_desarrollo.csv` debe ser `c13a9721648a864177d8a1e85de6f5e7e0823430596c3dd75e5d43da0e14aff9`, el mismo del contrato del BiLSTM B6. `datos_comunes/comun.py` comprueba además cada archivo contra el manifiesto al cargarlo.

No necesitas nada más: ni las fuentes originales, ni `unificado/`, ni los embeddings fastText (son solo del BiLSTM). El brazo USMSC con el que se entrenó B6 está dentro, en `ablacion_usmsc.csv`.

| Archivo | Para qué |
| --- | --- |
| `fragmentos_desarrollo.csv` | Todo el entrenamiento y la validación (2.878 fragmentos, 1.568 artículos) |
| `fragmentos_prueba_congelada.csv` | **Solo** para generar predicciones al final (sección 11) |
| `ablacion_satira.csv`, `ablacion_usmsc.csv`, `ablacion_politica.csv` | Filas extra de entrenamiento para los brazos de ablación |
| `pliegues.json` | Definición de los 3 pliegues |
| `manifest.json` y `REPORTE.md` | SHA-256, conteos y cómo se construyó |

Columnas que usa el modelo:

| Columna | Uso |
| --- | --- |
| `id_fragmento` | Identificador; va en las predicciones |
| `id_articulo` | Para agrupar fragmentos de un mismo artículo |
| `grupo` | Para la validación interna (la arma `datos_comunes`) |
| `fuente` | `v1`, `fakedes`, `polyglot` o `falledesinfo` |
| `texto` | **Única entrada del modelo**, como secuencia simple `[CLS] texto [SEP]` |
| `etiqueta_falsa` | **1 = falsa, 0 = real.** Coincide con tu `label` actual y con el BiLSTM B6: no hay que invertir nada |
| `peso` | Peso de la muestra en la pérdida (sección 6.2) |

Columnas que **no** entran al modelo: `dominio`, `tokens_bilstm`, `pliegue`. Son solo para auditoría.

| Pliegue | Entrena con | Evalúa en |
| --- | --- | --- |
| F1 | `fakedes` + `polyglot` | `v1` |
| F2 | `v1` + `polyglot` | `fakedes` |
| F3 | `v1` + `fakedes` | `polyglot` |

### 4.2. Dónde va cada cosa

Sigue el mapa de [`datasets/README.md`](../../datasets/README.md), que ya usa el BiLSTM:

```
datasets/
├── comun_v1/                    Conjunto común (del zip)
├── comun_v1_corridas/
│   ├── bilstm/                  Resultados del BiLSTM (de Orlando)
│   └── mbert/                   TUS resultados, misma estructura:
│       ├── M0/F1_s42/ …         una carpeta por corrida (config, métricas, predicciones.csv)
│       ├── M0/evaluacion/       métricas del evaluador común
│       ├── decisiones.json      registro de experimentos y decisiones
│       └── final/               modelo final, contrato.json, predicciones fuera de pliegue
├── bilstm_produccion/           BiLSTM que usa la app (de Orlando)
└── mbert_produccion/            mBERT que usa hoy la app (lo ordenas tú, sección 5)
    ├── conjunto/                datos con que se entrenó y evaluó
    ├── modelo/                  checkpoint (LFS), config y contrato
    └── evaluaciones/            pruebas de ese modelo
```

`datasets/` está fuera de Git salvo los pesos de producción que se suban con LFS (sección 5.3). Tus resultados de `comun_v1_corridas/mbert/` se los pasas a Orlando en un zip (sección 10).

---

## 5. Ordenar y limpiar antes de entrenar

Hazlo **antes** de crear el script nuevo, para entrenar ya sobre una carpeta limpia. Es lo mismo que hizo Orlando con el BiLSTM (ver [`bilstm/README.md`](../../bilstm/README.md) y [`datasets/README.md`](../../datasets/README.md)).

### 5.1. Guarda lo actual

1. Commit de todo lo que tienes (scripts, informes, `selection/`, `evaluations/`) en `mbert`, **sin borrar nada**. Así los resultados de octubre siguen siendo reproducibles desde el historial de Git.
2. Copia de seguridad de tus carpetas de datos locales (`datasets/processed/`, `datasets/audits/`, `datasets/raw/`, etc.) fuera del repositorio. Orlando no tiene esos archivos: solo tú puedes ordenarlos.

### 5.2. Estructura objetivo de `mBERT/`

```
mBERT/
├── entrenar.py          Único script de entrenamiento (sección 6), con subcomandos:
│                          corrida      un pliegue y una semilla (antes train_bilstm_step4.py)
│                          experimento  3 pliegues × 3 semillas (antes run_bilstm_step4_matrix.py)
│                          plan         experimentos en orden con la regla de decisión
│                          decidir      regla de decisión entre dos configuraciones
│                          final        modelo final y contrato
├── modelo.py            Modelos base (mbert, beto, roberta_bne, xlmr) con ruta, revisión y SHA-256;
│                        carga del modelo y del tokenizador. Lo usa también el backend
├── requirements.txt
├── tests/               Pruebas cortas en CPU con un conjunto sintético
├── docs/
│   ├── RESULTADOS_PRODUCCION.md     El mBERT que usa hoy la app: datos, métricas, límites
│   ├── RESULTADOS_MODELO_NUEVO.md   Experimentos con comun_v1 y modelo final
│   └── INFORME_TECNICO.md           Tu informe técnico actual
└── README.md            Qué hay, cómo se instala y cómo se entrena, paso a paso
```

Es la misma forma que `bilstm/`. Copia de [`bilstm/entrenar.py`](../../bilstm/entrenar.py) la estructura de subcomandos, la regla de decisión y la etapa final; cambia solo lo propio de un transformer.

- **Lo común no se copia:** la lectura del conjunto, los pliegues, la validación interna y la evaluación están en [`datos_comunes/`](../../datos_comunes/README.md). Impórtalos (`from comun import particiones`, `from evaluar_comun import …`), igual que el BiLSTM.
- **Un subcomando por paso, no un archivo por paso.** Lo que siga haciendo falta de `download_phase_…` pasa a una función de `modelo.py`.

### 5.3. Qué conservar, dónde y qué retirar

| Conservar | Dónde |
| --- | --- |
| Checkpoint que usa hoy la app (`mBERT/runs/BILSTM_ES_main_len512_seed43_…/best_model/`), su `config.json` y `selection.json` | `datasets/mbert_produccion/modelo/`, con LFS. Actualiza la regla de `.gitattributes` y la ruta de [`backend/models/mbert.py`](../../backend/models/mbert.py) (constantes `MBERT_ROOT`/`SELECTION`) |
| Tokenizador mBERT (`mBERT/assets/tokenizer_mbert_cased/`) | Junto al checkpoint de producción |
| Datos con que se entrenó y evaluó ese checkpoint (`datasets/processed/mbert_bilstm_step3_20261008_v1` y lo necesario de `audits/`) | `datasets/mbert_produccion/conjunto/` |
| `evaluations/` y `final_test_step7/` (resultados) | `datasets/mbert_produccion/evaluaciones/` los datos; el texto, resumido en `mBERT/docs/RESULTADOS_PRODUCCION.md` |
| Informes `PASO_3…`, `PASO_4…`, `PLAN_REENTRENAMIENTO…`, `REPORTE_PASO_5/6`, `MODELO_NUEVO_TARJETA.md` | Resumidos en `mBERT/docs/RESULTADOS_PRODUCCION.md`; los originales quedan en el historial |

| Retirar (queda en el commit de 5.1) |
| --- |
| `step1_…` a `step7_…`, sus variantes `v3`/`v4`, `run_bilstm_step4_matrix.py`, `summarize_bilstm_step4.py`, `select_bilstm_step5.py`, `download_phase_…` |
| Checkpoints de corridas de experimentos de octubre (todo `mBERT/runs/` salvo el de producción, que se mueve) |
| Copias de datos intermedias que no sean el conjunto de producción |
| La carpeta `mbert/` en minúsculas (`GUIA_DATOS_BILSTM_PARA_MBERT.md`): tiene rutas del BiLSTM anteriores a la limpieza. Retírala o actualízala |

### 5.4. Comprueba que la app sigue funcionando

1. Mueve el checkpoint de producción y actualiza **solo** las rutas de `backend/models/mbert.py` (en un commit aparte y avisando a Orlando, que también trabaja en el backend).
2. Pasa las pruebas del backend (`backend/tests/`) y comprueba que el backend carga mBERT y predice.
3. Commit y `git push origin mbert`.

Antes de borrar checkpoints o datos, confirma con Orlando que no los necesita la app ni la calibración conjunta.

---

## 6. Script único de entrenamiento

Crea `mBERT/entrenar.py` a partir de [`mBERT/train_bilstm_step4.py`](../../mBERT/train_bilstm_step4.py) (que queda en el historial). Mantén lo que ya hace bien: hashes, una carpeta por corrida con `exist_ok=False`, recarga explícita del mejor checkpoint y comprobación de la métrica.

### 6.1. Lista de cambios

| # | Antes (`train_bilstm_step4.py`) | Después (`entrenar.py corrida`) |
| --- | --- | --- |
| 1 | `DATA = datasets/processed/mbert_bilstm_step3_20261008_v1`, JSONL | `particiones(pliegue, brazo)` de `datos_comunes/comun.py`: lee `datasets/comun_v1/`, verifica los SHA-256 y devuelve entrenamiento, validación interna y la fuente que queda fuera |
| 2 | `--arm main\|no_usmsc` | `--pliegue F1\|F2\|F3\|todo` y `--brazo satira usmsc politica` (cero, uno o varios; mismos nombres que el BiLSTM) |
| 3 | `MODEL` fijo en mBERT | `--modelo mbert\|beto\|roberta_bne\|xlmr`, con ruta local, revisión y SHA-256 en `modelo.py` |
| 4 | `LENGTHS = (128,192,256,512)` | `--max-length`, por defecto 256 |
| 5 | `SEEDS = (42,43,44)` y `assert args.epochs == 3` | `--semilla` y `--epocas` libres; sin `assert` |
| 6 | `learning_rate=2e-5` fijo | `--lr`, por defecto 2e-5 |
| 7 | Pérdida sin pesos | Pérdida ponderada con la columna `peso` (sección 6.2) |
| 8 | Elegir época con la validación de 132 | Elegir época con la **validación interna** que devuelve `particiones` (sección 6.3) |
| 9 | `predictions_validation.jsonl` con `pred` | `predicciones.csv` con **logits** de la fuente que quedó fuera, en el formato común (sección 6.4) |
| 10 | `save_total_limit=None` | `save_only_model=True`, `save_total_limit=1`; `--no-guardar-modelo` para las corridas de experimento |
| 11 | Métricas propias en `score()` | Mantener `score()` para el registro; las métricas oficiales las calcula `datos_comunes/evaluar_comun.py` |

### 6.2. Pérdida ponderada

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

- Incluye `peso` en el `Dataset`, usa `remove_unused_columns=False` y asegúrate de que el `DataCollatorWithPadding` lo deja pasar como tensor `float`.
- Iguala además el peso total de reales y falsas, como `pesos_de_clase()` en [`bilstm/entrenar.py`](../../bilstm/entrenar.py).
- **Comprobación:** en la primera corrida, registra en el log la suma de pesos por clase. Debe quedar cerca de 1:1.

### 6.3. Validación interna para elegir la época

- **Usa la que devuelve `particiones()`:** 10 % de los grupos del entrenamiento del pliegue, **fija por pliegue y la misma que usó el BiLSTM**. No armes otra con `GroupShuffleSplit`.
- Evalúa cada época en ella y elige por F1 macro **de artículo** (media de las probabilidades de sus fragmentos), con empate a favor de la época anterior.
- **La fuente que quedó fuera no se usa para elegir la época.** Solo se predice con el mejor checkpoint al terminar.

### 6.4. Predicciones de salida

Con el mejor checkpoint, predice **todos los fragmentos de la fuente que quedó fuera** y escribe `predicciones.csv` en la carpeta de la corrida, con las mismas columnas que el BiLSTM:

```python
logits = trainer.predict(test_ds).predictions          # forma (n, 2): [real, falsa]
prob = torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1)[:, 1]
pd.DataFrame({
    "id_fragmento": ids,
    "modelo": args.modelo,
    "configuracion": nombre_config,      # p. ej. "M1a"
    "semilla": args.semilla,
    "pliegue": args.pliegue,
    "logit_real": logits[:, 0],
    "logit_falsa": logits[:, 1],
    "prob_falsa": prob.numpy(),
}).to_csv(out / "predicciones.csv", index=False)
```

- Los logits se guardan en `float32`, aunque el modelo corra en BF16.
- La salida 1 del modelo es «falsa» (`id2label = {0: "real", 1: "falsa"}`).
- Escribe también `config.json` (argumentos, revisión y SHA-256 del modelo base, SHA-256 de `fragmentos_desarrollo.csv`, SHA-256 del script) y `resultados.json` (época elegida e historial de la validación interna).

### 6.5. Subcomandos `experimento`, `plan` y `decidir`

- `experimento NOMBRE [opciones]`: lanza los 3 pliegues × 3 semillas en serie, en `datasets/comun_v1_corridas/mbert/NOMBRE/`, y llama a `datos_comunes/evaluar_comun.py`. Si una corrida falla, se detiene y no la repite en silencio. Las corridas ya terminadas no se repiten.
- `plan`: ejecuta la sección 7 en orden y escribe `decisiones.json`.
- `decidir A B [--brazo]`: aplica la regla a dos configuraciones ya evaluadas.

**Antes de seguir:** prueba corta (1 época, un pliegue) que genera un `predicciones.csv` que el evaluador común acepta, y tests en `mBERT/tests/` con un conjunto sintético en CPU (mira [`bilstm/tests/test_entrenar.py`](../../bilstm/tests/test_entrenar.py)).

---

## 7. Experimentos, en orden

Cada experimento es **una configuración × 3 pliegues × 3 semillas = 9 corridas**. A 256 tokens con unos 2.900 fragmentos: unos 3 minutos por corrida con mBERT o BETO y unos 6 con XLM-R. Unos **30 minutos por experimento**, una hora con XLM-R.

**Regla para adoptar un cambio** (la misma que el BiLSTM): la media de F1 macro de artículo en los 3 pliegues debe subir **al menos 0,02** y la tasa de falsas alarmas no debe subir más de 2 puntos. Si la diferencia es menor, gana la opción más barata. Un brazo de ablación, además, debe mejorar al menos 2 de los 3 pliegues.

**Cambia una sola cosa por experimento** respecto al ganador anterior.

| Paso | ID | Configuración | Pregunta |
| --- | --- | --- | --- |
| 0 | **M0** | `mbert`, 256 tokens, lr 2e-5, 3 épocas, decaimiento 0,01, calentamiento 10 %, lote efectivo 16, BF16, pesos por muestra | ¿Cuánto rinde la receta actual con los datos y la validación nuevos? |
| 0 | **M0-len** | Comprobación: % de fragmentos truncados a 256 con cada tokenizador | Registrar el dato; es lo que mide M2c |
| 1R | **Prueba rápida** | M0, M1a y M1b con **solo la semilla 42** (3 corridas cada uno) | ¿Merece la pena el paso 1 completo? |
| 1 | **M1a** | `beto`, resto igual que M0 | ¿BETO supera a mBERT? |
| 1 | **M1b** | `roberta_bne` (MarIA), resto igual que M0 | ¿MarIA supera a mBERT? |
| 1 | **M1c** | `xlmr`, resto igual que M0 | ¿Y un multilingüe más fuerte? |
| 2 | **M2a** | Ganador del paso 1 con lr 1e-5 y hasta 5 épocas | ¿Aprende mejor más despacio? |
| 2 | **M2b** | Ganador del paso 1 con lr 3e-5 y hasta 3 épocas | ¿O más rápido? |
| 2 | **M2c** | Ganador de M2a/M2b con 512 tokens (microlote 2, acumulación 8, *gradient checkpointing*) | ¿Leer más del fragmento ayuda? |
| 3 | **M3b** | Ganador + brazo `usmsc` | ¿USMSC ayuda también a mBERT? (al BiLSTM le dio +0,06) |
| 3 | **M3a** | Ganador + brazo `satira` | ¿La sátira ayuda o confunde? |
| 3 | **M3c** | Ganador + brazo `politica` | ¿Las parejas sintéticas enseñan algo transferible? |
| 4 | **M4** (opcional) | Ganador + cabeza adversarial de fuente (sección 7.1) | ¿Quitar la información de medio mejora la generalización? |

Notas:

- **Prueba rápida (1R).** Si BETO o MarIA quedan **más de 0,02 por debajo** de M0, se descartan sin más corridas. Si quedan cerca o por encima, se completan sus semillas 43 y 44 y se decide con la regla. **No decidas nunca con una sola semilla.**
- **Paso 1.** Los modelos compiten contra M0 y entre ellos. Si dos quedan a menos de 0,02, gana el más pequeño y rápido (BETO > MarIA > mBERT > XLM-R). **Se prueban varios, pero a la app solo llega uno:** el ganador sustituye a mBERT; nunca se usan a la vez.
- **Paso 2.** M2a y M2b compiten contra el ganador del paso 1. Después, M2c compara la longitud. Si 512 no gana por 0,02, se queda 256.
- **Paso 3.** Cada brazo se compara contra el ganador del paso 2. M3b va primero porque es el que funcionó en el BiLSTM. Si se adopta, M3a y M3c se prueban sobre él.
- **Referencias.** Orlando ya calculó las de solo longitud y TF-IDF con estos mismos pliegues (`datasets/comun_v1_corridas/referencias/`). Compara tu ganador con ellas.
- **No añadas experimentos** sin acordarlo con Orlando: cada experimento extra aumenta la probabilidad de ganar por azar.
- **Registra cada decisión** en `decisiones.json` y en `mBERT/docs/RESULTADOS_MODELO_NUEVO.md`. Si eliges a mano en contra de la regla, escribe el motivo.

### 7.1. Cabeza adversarial de fuente (opcional, M4)

Solo si los pasos 1–3 terminaron y queda tiempo.

- Segunda cabeza lineal que predice la `fuente` desde el mismo vector `[CLS]`, con una **capa de inversión de gradiente** entre el vector y esa cabeza.
- Pérdida total = pérdida de clase + λ × pérdida de fuente, con λ = 0,1 fijo.
- En cada pliegue hay 2 fuentes de entrenamiento, así que la cabeza de fuente es binaria. En inferencia se descarta; el contrato no cambia.

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

## 8. Modelo final

Igual que `bilstm/entrenar.py final`:

1. **Entrena la configuración ganadora con todo el desarrollo** (`--pliegue todo`), con 3 semillas, en `datasets/comun_v1_corridas/mbert/final/todo_s<semilla>/`. Épocas: la mediana de las elegidas en las 9 corridas por pliegue. Sin validación interna.
2. **Guarda las predicciones fuera de pliegue** del ganador (las 9 corridas) en `final/predicciones_fuera_de_pliegue.csv`.
3. **Semillas:** Orlando decide, con esas predicciones, si promediar los logits de las 3 semillas compensa triplicar el tiempo de inferencia (umbral: +0,01 de F1).
4. **No calibres tú.** Orlando ajusta la temperatura con las predicciones fuera de pliegue de los dos modelos a la vez, para que calibración y combinación sean coherentes, y te devuelve `T`.

---

## 9. Contrato de inferencia

El backend ([`backend/models/mbert.py`](../../backend/models/mbert.py)) lee hoy `mBERT/selection/bilstm_step5_20261008_v1/selection.json` y **exige `max_length == 512`** y el tokenizador mBERT. Con un modelo nuevo esa comprobación falla, así que Orlando adaptará el backend para leer este contrato. **Usa los mismos nombres de campos que el contrato del BiLSTM B6** (`datasets/comun_v1_corridas/bilstm/final/contrato.json`), para que el backend lea los dos con el mismo código:

```json
{
  "modelo": "mbert",
  "version": "comun_v1.1_M1a_20261120",
  "eleccion": {"ganador_regla": "M1a", "manual": false},
  "modelo_base": {"clave": "beto", "hub_id": "dccuchile/bert-base-spanish-wwm-cased", "revision": "…", "sha256": "…"},
  "etiquetas": {"real": 0, "falsa": 1},
  "max_tokens": 256,
  "entrada": "texto_unico",
  "temperatura": 1.0,
  "temperatura_provisional": true,
  "umbral_falsa": 0.5,
  "semillas": [42, 43, 44],
  "promediar_logits_semillas": true,
  "epocas": 3,
  "checkpoints": {
    "s42": {"ruta": "datasets/comun_v1_corridas/mbert/final/todo_s42/best_model", "sha256": "…"}
  },
  "tokenizador": {"ruta": "datasets/comun_v1_corridas/mbert/final/todo_s42/best_model", "sha256_tokenizer_json": "…"},
  "sha256_conjunto": "c13a9721648a864177d8a1e85de6f5e7e0823430596c3dd75e5d43da0e14aff9"
}
```

- `sha256_conjunto` es el de `fragmentos_desarrollo.csv`, igual que en B6.
- `etiquetas` en minúsculas, igual que en B6. El orden de salidas del modelo debe coincidir.
- `eleccion`: si eliges a mano, `"manual": true`, `ganador_elegido` y `motivo`.
- `temperatura` la rellena Orlando tras la calibración; mantén los hashes, el backend los verifica antes de cargar.
- Cuando el modelo nuevo pase a producción, se copiará a `datasets/mbert_produccion/modelo/` con LFS y la `ruta` cambiará allí.

---

## 10. Entrega y unión con `develop`

1. **A Orlando, en un zip** (no van a Git): `datasets/comun_v1_corridas/mbert/` sin checkpoints de experimentos, es decir, `predicciones.csv`, `config.json`, `resultados.json` y `evaluacion/` de cada corrida, `decisiones.json` y `final/` (con su `contrato.json` y las predicciones fuera de pliegue). Los pesos finales van aparte (son grandes).
2. **En Git, rama `mbert`:** `mBERT/` ordenado (`entrenar.py`, `modelo.py`, `tests/`, `docs/`, `README.md`), `datasets/mbert_produccion/modelo/` con LFS si lo moviste, y el cambio de rutas en `backend/models/mbert.py` si lo hubo.
3. **Antes de la PR:** vuelve a traer `develop` (`git merge origin/develop`), pasa `mBERT/tests/`, `bilstm/tests/`, `datos_comunes/tests/` y `backend/tests/`, y comprueba que la app carga los dos modelos.
4. **PR de `mbert` hacia `develop`** (nunca hacia `main`). Orlando la revisa y la une.

---

## 11. Prueba congelada

Solo cuando Orlando lo indique, con el modelo final ya fijado:

1. Predice `fragmentos_prueba_congelada.csv` con el modelo final (y con las 3 semillas si se entregan).
2. Guarda `predicciones_congelada.csv` con el formato de la sección 6.4 y `pliegue = "congelada"`.
3. **Entrégalo sin calcular métricas.** El evaluador común lo hace una sola vez para los dos modelos.

---

## 12. Lista de comprobación

**A. Rama y entorno**
- [ ] `develop` traída a `mbert` y subida.
- [ ] Git LFS instalado; los pesos de producción se ven completos.
- [ ] Modelos base descargados, con revisión y SHA-256 registrados.

**B. Datos**
- [ ] `datasets/comun_v1/` del zip, versión 1.1, SHA-256 de `fragmentos_desarrollo.csv` verificado.

**C. Orden y limpieza**
- [ ] Commit de todo lo actual y copia de tus datos locales.
- [ ] Producción en `datasets/mbert_produccion/` y ruta del backend actualizada; la app carga mBERT.
- [ ] `mBERT/` con la estructura de la sección 5.2; retirado lo de la tabla 5.3; carpeta `mbert/` resuelta.

**D. Script**
- [ ] `entrenar.py` con los 11 cambios de la sección 6.1, usando `datos_comunes`.
- [ ] Prueba corta con `predicciones.csv` válido y pesos por clase equilibrados; tests en `mBERT/tests/`.

**E. Experimentos**
- [ ] M0 y M0-len.
- [ ] Prueba rápida 1R y paso 1 (M1a–M1c) con decisión anotada.
- [ ] Paso 2 (M2a–M2c) con decisión anotada, incluida la longitud.
- [ ] Paso 3 (M3b, M3a, M3c) con decisión anotada.
- [ ] (Opcional) M4.

**F–H. Final, entrega y prueba congelada**
- [ ] Modelo final con 3 semillas y predicciones fuera de pliegue.
- [ ] Contrato con los campos de la sección 9; `temperatura` recibida de Orlando.
- [ ] `mBERT/docs/RESULTADOS_PRODUCCION.md`, `RESULTADOS_MODELO_NUEVO.md` y `mBERT/README.md` completos.
- [ ] Zip de resultados entregado a Orlando.
- [ ] PR de `mbert` hacia `develop` con todos los tests pasando.
- [ ] Predicciones de la prueba congelada entregadas sin mirar métricas.

---

## 13. Preguntas frecuentes

**¿Por qué no seguir con 512 tokens si ganaba en validación?**
No se descarta: se vuelve a medir en M2c. Pero el resultado anterior tiene tres límites:

- `main/512` ganó a `main/256` por **0,0103** (0,9220 frente a 0,9117) en 132 filas, apenas por encima del margen de empate de 0,01 que tú mismo fijaste.
- La validación eran artículos completos (mediana de 629 subpalabras) en los que las falsas son más cortas. A 512 el modelo ve más de esa diferencia de longitud.
- En la externa, el modelo de 512 rindió 0,718 en textos de menos de 200 palabras y 0,414 en los de 1.000 o más.

Al BiLSTM le pasó lo mismo: 320 tokens no mejoró a 192 con la validación por fuente (B8).

**¿Por qué quitar USMSC si subía la validación?**
Subía una validación de 132 filas de dos fuentes. Ahora se mide como brazo (M3b) con validación por fuente. En el BiLSTM sí ayudó, así que es probable que se adopte.

**¿Y si ningún modelo nuevo supera a mBERT por 0,02?**
Se queda mBERT con la receta ganadora. La mejora viene entonces de los datos nuevos, de la calibración y de la combinación con el BiLSTM. Es un resultado válido.

**¿Puedo mirar la externa de 569 para ver cómo voy?**
No para decidir nada. Ya se consultó muchas veces y premia la longitud del artículo. La referencia ahora son los 3 pliegues.

**¿Qué pasa con el pliegue F3 (Polyglot)?**
Ahí las reales son todas de El Mundo y las falsas de medios de propaganda (probablemente traducidas), así que es fácil acertar por el medio. Se informa, pero no decide solo: la regla usa la media de los tres pliegues y, para los brazos, exige mejora en al menos dos.

**¿Mis cifras van a ser mucho más bajas que 0,939?**
Sí, y es lo esperado: ahora cada fuente se evalúa con un modelo que nunca la vio y sin atajos de longitud. El BiLSTM B6 saca 0,585. Lo que importa es comparar contra M0, las referencias y el BiLSTM con el mismo protocolo.

---

## 14. Instrucción para tu asistente de IA

Si usas un asistente de programación, abre la raíz del repositorio en tu rama `mbert` (después de la fase A) y pégale este texto:

```text
Vas a ayudarme a ejecutar el plan de mejora de mBERT de este repositorio (ScanTrue,
detector de noticias falsas en español). El plan completo está en
docs/mejora_modelos/03_PLAN_MBERT.md: léelo entero antes de hacer nada, junto con
docs/mejora_modelos/01_PLAN_COMUN.md, datasets/README.md, datos_comunes/README.md,
bilstm/README.md y bilstm/entrenar.py (es el modelo de referencia: mi script debe
tener la misma forma).

Contexto:
- Trabajo en la rama `mbert`, que ya tiene traída `develop`. Nunca hagas commit,
  merge ni push en `main`. No hagas push sin preguntarme.
- Mi equipo: RTX 5060 de 8 GB, BF16, Python 3.14 y las versiones del plan (sección 3.2).
- El conjunto común está en datasets/comun_v1/ (versión comun_v1.1). No lo modifiques.
- Etiquetas: 1 = falsa, 0 = real (columna etiqueta_falsa). La salida 1 del modelo es «falsa».
- Lo común con el BiLSTM (datos, pliegues, validación interna, evaluador, formato de
  predicciones y contrato) se usa desde datos_comunes/; no lo reescribas ni lo copies.
- No modifiques bilstm/, datos_comunes/ ni frontend/. En backend/ solo puedes cambiar
  las rutas de backend/models/mbert.py, en un commit aparte.
- Nunca abras ni evalúes fragmentos_prueba_congelada.csv hasta que yo lo diga.
- No uses la externa de 569, la prueba de 146 ni la validación de 132 para decidir nada.

Cómo trabajar:
1. Sigue las fases del plan en orden (B, C, D, E, F, G). Al terminar cada fase,
   detente, resúmeme qué hiciste y qué comprobaste, y espera mi confirmación.
2. Fase C (orden y limpieza): antes de mover o borrar nada, haz un commit de todo lo
   actual y enséñame la lista exacta de lo que vas a mover, a dónde, y lo que vas a
   retirar. No borres nada sin mi confirmación. Después comprueba que el backend sigue
   cargando mBERT y que pasan backend/tests/.
3. Fase D: crea mBERT/entrenar.py (subcomandos corrida, experimento, plan, decidir,
   final) y mBERT/modelo.py, con los 11 cambios de la sección 6.1, y tests en
   mBERT/tests/ con un conjunto sintético en CPU. Haz una corrida corta (1 época, un
   pliegue) y comprueba que datos_comunes/evaluar_comun.py acepta su predicciones.csv.
4. Fase E: ejecuta los experimentos en el orden de la sección 7, empezando por M0 y la
   prueba rápida 1R. Lanza los entrenamientos largos en segundo plano y guarda todo en
   datasets/comun_v1_corridas/mbert/. Aplica la regla de decisión tal cual; nunca
   decidas con una sola semilla. Si propones elegir algo en contra de la regla,
   pregúntame y anota el motivo. No añadas experimentos fuera de la lista.
5. Borra el best_model de cada corrida de experimento en cuanto tenga su
   predicciones.csv, para no llenar el disco.
6. Registra cada decisión en decisiones.json y en mBERT/docs/RESULTADOS_MODELO_NUEVO.md.
7. Si algo del plan no cuadra con lo que encuentras en mis archivos, para y pregúntame
   en vez de suponer.

Empieza por la fase B: verifica datasets/comun_v1/ (versión y SHA-256 de
fragmentos_desarrollo.csv, sección 4.1) y dime qué encuentras.
```

