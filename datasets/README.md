# Datos y modelos de ScanTrue

Esta carpeta está fuera de Git (salvo este README). Reorganizada el 10 de noviembre de 2026.

```
datasets/
├── fuentes/                 Datasets descargados, tal como vienen
│   ├── CATALOGO.md          Descripción de cada dataset
│   ├── usadas/              Los que alimentan al modelo de producción o al conjunto común
│   └── no_usadas/           Descargados pero sin usar por ningún modelo
├── unificado/               Todos los textos de las fuentes en un solo CSV (entrada del conjunto común)
├── embeddings/              Vectores fastText CC español (cc.es.300.vec.gz)
├── bilstm_produccion/       BiLSTM que usa hoy la app
│   ├── conjunto/            Particiones con que se entrenó y evaluó
│   ├── modelo/              Checkpoint, config, historial y resultados
│   └── evaluaciones/        Predicciones de la prueba externa y estudio de longitud mínima
├── mbert_produccion/        mBERT que usa hoy la app (ver mBERT/docs/RESULTADOS_PRODUCCION.md)
│   ├── conjunto/            Datos con que se entrenó y evaluó
│   ├── modelo/              Checkpoint (LFS), tokenizador, selection.json y config
│   └── evaluaciones/        Predicciones y métricas de validación, prueba y externa
├── modelos_base/            Modelos base de Hugging Face para mBERT (mbert/, beto/, …)
├── comun_v1/                Conjunto común (versión 1.1), el mismo para BiLSTM y mBERT
└── comun_v1_corridas/       Resultados con el conjunto común
    ├── referencias/         Referencias: solo longitud y TF-IDF
    ├── bilstm/              Experimentos B0–B8, decisiones.json y modelo final B6 (final/)
    └── respaldo_v1.0/       Solo métricas de la versión 1.0 del conjunto
```

## Fuentes usadas

| Carpeta | Dataset | Producción | Conjunto común |
| --- | --- | :---: | :---: |
| `spanish_fake_news_corpus_v1/` | Spanish Fake News Corpus v1 (xlsx original y copia CSV de sayalaruano) | ✅ | ✅ (F1; su sátira solo en ablación) |
| `fakedes_iberlef_2021/` | FakeDeS, IberLEF 2021 | ✅ prueba externa | ✅ (F2) |
| `polyglotfakefacts_v2/` | PolyglotFakeFacts v2, parte en español | ✅ | ✅ (F3) |
| `falledesinfo_es/` | FalleDesinfo_ES | ✅ prueba externa | ✅ solo prueba congelada |
| `usmsc_edds/` | USMSC y su versión corregida de Edds | ✅ | ✅ brazo de ablación (usado en B6) |
| `spanish_political_fake_news/` | Spanish Political Fake News | — | brazo de ablación (rechazado) |

## Fuentes no usadas

Acosta, Zenodo, FakeCovid, FLARES, RUN-AS, FactOReS, MM-COVID (descarga pendiente) y X-FACT. X-FACT y FactOReS pueden servir para probar la verificación del incremento 2.

## Cómo se relacionan

- `unificado/todos_los_textos_unicos.csv` se generó con el antiguo `bilstm/unificar_todos.py` (historial de Git, commit `d4ece74`) a partir de `fuentes/`. Su SHA-256 está en `comun_v1/manifest.json`.
- `comun_v1/` se construye con `datos_comunes/construir_comun.py` desde `unificado/`. Reconstruirlo da los mismos fragmentos byte a byte.
- `bilstm_produccion/` se creó con los scripts antiguos (mismo commit). `bilstm_produccion/modelo/config.json` conserva las rutas de entonces.

## Qué se borró el 10 nov 2026

Copias duplicadas (`MIS DATASETS/`, su `.zip`; la carpeta `DATASETS/` de la raíz queda pendiente de borrar a mano), etapas intermedias (`estandarizados/`, `unificado_total/` salvo el CSV de entrada), los embeddings `wiki.es.vec`, los checkpoints de experimentos (de octubre y de B0–B8) y el respaldo completo de `comun_v1` 1.0 (quedan sus métricas).
