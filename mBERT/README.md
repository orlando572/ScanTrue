# mBERT de ScanTrue

Clasificador de noticias falsas en español basado en un transformer. Plan en curso: [docs/mejora_modelos/03_PLAN_MBERT.md](../docs/mejora_modelos/03_PLAN_MBERT.md).

```
mBERT/
├── entrenar.py          Único script de entrenamiento: corrida, experimento, truncado, plan, decidir, final
├── modelo.py            Modelos base (mbert, beto, roberta_bne, xlmr): revisión fijada, SHA-256, descarga y carga
├── requirements.txt
├── tests/               Pruebas cortas en CPU con un conjunto sintético y un BERT diminuto
├── docs/
│   ├── RESULTADOS_PRODUCCION.md     El mBERT que usa hoy la app: datos, métricas, límites
│   ├── RESULTADOS_MODELO_NUEVO.md   Experimentos con comun_v1 y modelo final (fase E)
│   └── INFORME_TECNICO.md           Informe técnico de los entrenamientos de octubre
└── README.md
```

Los datos y los modelos viven en `datasets/` (ver [datasets/README.md](../datasets/README.md)):

| Carpeta | Contenido | En Git |
| --- | --- | --- |
| `datasets/mbert_produccion/modelo/` | Checkpoint que usa la app, tokenizador y `selection.json` | Sí (pesos con LFS) |
| `datasets/mbert_produccion/conjunto/`, `evaluaciones/` | Datos y evaluaciones de ese checkpoint | No |
| `datasets/modelos_base/` | Modelos base descargados de Hugging Face (`mbert/`, después `beto/`, …) | No |
| `datasets/comun_v1/` | Conjunto común, el mismo que el BiLSTM | No |
| `datasets/comun_v1_corridas/mbert/` | Resultados de los experimentos nuevos | No |

## Instalación (Windows)

Python 3.14 y una GPU con CUDA 13 (se usó una RTX 5060 de 8 GB, BF16). Desde la raíz del repositorio:

```powershell
py -3.14 -m venv mBERT\.venv
.\mBERT\.venv\Scripts\python.exe -m pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130
.\mBERT\.venv\Scripts\python.exe -m pip install -r mBERT\requirements.txt
```

Git LFS es obligatorio para los pesos de producción: `git lfs install` una vez y `git lfs pull` después de clonar. Sin LFS, `model.safetensors` es un puntero de 3 líneas y el backend no carga mBERT.

## Entrenar

Todo desde la raíz del repositorio. Los modelos base se descargan una vez, con la revisión fijada en `modelo.py`:

```powershell
.\mBERT\.venv\Scripts\python.exe mBERT\modelo.py descargar beto xlmr
.\mBERT\.venv\Scripts\python.exe mBERT\modelo.py verificar
```

Una corrida (un pliegue, una semilla), un experimento (3 pliegues × 3 semillas, evaluado con `datos_comunes/evaluar_comun.py`) y el plan completo de la sección 7:

```powershell
.\mBERT\.venv\Scripts\python.exe mBERT\entrenar.py corrida --pliegue F1 --semilla 42 --configuracion prueba --salida datasets\comun_v1_corridas\mbert\prueba\F1_s42 --epocas 1 --no-guardar-modelo
.\mBERT\.venv\Scripts\python.exe mBERT\entrenar.py experimento M1a --modelo beto
.\mBERT\.venv\Scripts\python.exe mBERT\entrenar.py plan
```

- Entrada: solo `texto`, como secuencia única, truncada a `--max-length` (256 por defecto, incluidos `[CLS]` y `[SEP]`).
- Pérdida ponderada con `peso` × peso de clase (reales y falsas suman lo mismo; `config.json` registra la suma).
- La época se elige con la validación interna del pliegue (F1 macro de artículo, empate a favor de la anterior). El mejor estado se guarda en memoria y se recarga, comprobando que reproduce su F1; no se escriben checkpoints por época.
- Cada corrida escribe `config.json` (argumentos, modelo base con revisión y SHA-256, SHA-256 del conjunto y del script, fracción truncada), `resultados.json` y `predicciones.csv` con logits en el formato común.
- Prueba congelada: nunca se abre (lo impide `datos_comunes/comun.py`).

Pruebas:

```powershell
.\mBERT\.venv\Scripts\python.exe -m unittest discover -s mBERT/tests
```

## Modelo de producción

`google-bert/bert-base-multilingual-cased`, 512 tokens, semilla 43, etiquetas `0=REAL`, `1=FALSA`, umbral 0,5. F1 macro 0,9385 en su validación de 132 y **0,600** en la externa de 569 (150 de 307 reales marcadas falsas). Detalle y límites en [docs/RESULTADOS_PRODUCCION.md](docs/RESULTADOS_PRODUCCION.md). Lo carga [`backend/models/mbert.py`](../backend/models/mbert.py), que verifica los SHA-256 antes de inferir.

Los scripts de octubre (preparación, matriz de entrenamiento, selección, evaluación e inferencia manual) se retiraron el 10 nov 2026 y están en el historial de Git (commit `ece259a`).
