# Mejora de los modelos de ScanTrue

Plan para mejorar el BiLSTM y mBERT con los datasets que ya existen. No incluye datasets nuevos ni los incrementos del proyecto.

| Documento | Para quién | Contenido |
| --- | --- | --- |
| [00_ANALISIS_DATASETS.md](00_ANALISIS_DATASETS.md) | Ambos | Inventario de los datasets, duplicados entre carpetas, atajos medidos y búsqueda de datasets adicionales |
| [01_PLAN_COMUN.md](01_PLAN_COMUN.md) | Ambos | Conjunto común, validación por fuente, calibración, combinación y reglas de decisión |
| [02_PLAN_BILSTM.md](02_PLAN_BILSTM.md) | Orlando | Cambios de código, experimentos y entrega del BiLSTM |
| [03_PLAN_MBERT.md](03_PLAN_MBERT.md) | Responsable de mBERT | Plan detallado y autocontenido para mBERT |

## Hallazgos clave

- Los dos modelos entrenaron con casi los mismos datos y obtienen el mismo F1 externo (0,603 y 0,600). Un clasificador que solo cuenta palabras saca 0,663 en esa misma prueba.
- Solo hay **1.960 artículos limpios** con ambas clases (v1, FakeDeS y Polyglot sin sátira ni redes sociales).
- La fuente política tiene falsas sintéticas por cambio de nombres, y USMSC son fragmentos truncados sin procedencia. Pasan a brazos de ablación.
- En el nivel «Muy probablemente falso» de la extensión, solo el 60 % de los textos son falsos.

## Orden de trabajo

1. ✅ Orlando construye `datasets/comun_v1/` (versión 1.1) y el evaluador común (`datos_comunes/`).
2. Cada responsable ejecuta los experimentos de su modelo, en paralelo. ✅ BiLSTM: ganador B6 ([resultados](../../bilstm/docs/RESULTADOS_MODELO_NUEVO.md)). Pendiente: mBERT, en su rama `mbert` partiendo de `develop` ([03_PLAN_MBERT.md](03_PLAN_MBERT.md)).
3. Orlando calibra, combina y comprueba los niveles de la extensión.
4. Prueba congelada, una sola vez.
5. Se actualizan los contratos de inferencia y el backend.
