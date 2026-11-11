# BiLSTM de ScanTrue

Clasificador de **noticias en español**: recibe el titular y el texto y devuelve la probabilidad de que la noticia sea falsa. Es orientativo: no verifica hechos con evidencia.

## Carpetas y archivos

```
bilstm/
├── entrenar.py          Único script de entrenamiento (subcomandos más abajo)
├── modelo.py            Arquitectura del BiLSTM y tokenizador; también los usa el backend
├── requirements.txt     Dependencias
├── tests/
│   └── test_entrenar.py Pruebas del modelo, del entrenamiento y de la regla de decisión
└── docs/
    ├── RESULTADOS_PRODUCCION.md   Modelo de octubre, archivado (datos, métricas y límites)
    ├── RESULTADOS_MODELO_NUEVO.md Experimentos B0–B8 con el conjunto común y modelo B6
    ├── TEORIA_ENTRENAMIENTO.md    Teoría básica del entrenamiento de un BiLSTM
    └── INSTALACION_WINDOWS.md     Instalación con GPU en Windows 11
```

Código compartido con mBERT en [`datos_comunes/`](../datos_comunes/README.md): construye el conjunto común, lee los pliegues y evalúa. Datos y modelos en [`datasets/`](../datasets/README.md) (fuera de Git).

## Los dos modelos

| | B6, en producción desde el 11 nov 2026 | Modelo de octubre (archivado, sin uso) |
| --- | --- | --- |
| Checkpoint | `datasets/bilstm_produccion/modelo/modelo.pt` (copia de `datasets/comun_v1_corridas/bilstm/final/todo_s42/`) | `datasets/bilstm_produccion/archivo_octubre/modelo/mejor_modelo.pt` |
| Datos | `datasets/comun_v1/` + brazo USMSC | `datasets/bilstm_produccion/archivo_octubre/conjunto/` |
| Etiquetas | salida 0 = real, 1 = falsa | salida 0 = falsa, 1 = real |
| Calibración | temperatura T = 8,4468 en `contrato.json` (calibración conjunta) | ninguna |
| Resultados | [RESULTADOS_MODELO_NUEVO.md](docs/RESULTADOS_MODELO_NUEVO.md) | [RESULTADOS_PRODUCCION.md](docs/RESULTADOS_PRODUCCION.md) |

Los dos usan la misma arquitectura (`modelo.py`: fastText CC 300 d → BiLSTM de 64 por dirección → estado final → lineal) y leen como máximo 192 tokens. El backend carga B6 a través de su `contrato.json` y lo combina con BETO (20 % BiLSTM, 80 % BETO, [04_CALIBRACION_CONJUNTA.md](../docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md)).

## Preparar el entorno

Python 3.14.4 en `bilstm/.venv`, con [`requirements.txt`](requirements.txt) y la versión de PyTorch adecuada para tu GPU ([selector oficial](https://pytorch.org/get-started/locally/)). En Windows, sigue [INSTALACION_WINDOWS.md](docs/INSTALACION_WINDOWS.md). El entrenamiento necesita `datasets/embeddings/cc.es.300.vec.gz` y `datasets/comun_v1/`.

## Entrenar

Todo se hace con `bilstm/entrenar.py`, desde la raíz del repositorio. Los resultados se guardan en `datasets/comun_v1_corridas/` (se cambia con `--corridas`).

| Paso | Comando | Qué hace |
| --- | --- | --- |
| 1 | `bilstm/.venv/bin/python bilstm/entrenar.py corrida --pliegue F1 --semilla 42 --configuracion prueba --salida datasets/comun_v1_corridas/prueba` | Entrena un pliegue con una semilla. Útil para probar algo rápido |
| 2 | `bilstm/.venv/bin/python bilstm/entrenar.py experimento B6 --brazo usmsc` | 3 pliegues × 3 semillas de una configuración y su evaluación |
| 3 | `bilstm/.venv/bin/python bilstm/entrenar.py plan` | Ejecuta B0–B8 en orden y aplica la regla de decisión; escribe `bilstm/decisiones.json` |
| 4 | `bilstm/.venv/bin/python bilstm/entrenar.py decidir B6 B0 --brazo` | Compara dos configuraciones ya evaluadas |
| 5 | `bilstm/.venv/bin/python bilstm/entrenar.py final --ganador B6 --motivo "…"` | Modelo final con todo el desarrollo, temperatura y `contrato.json`. Sin `--ganador` usa el de la regla |

Las referencias (solo longitud y TF-IDF) se calculan con `datos_comunes/referencias.py`. Opciones del modelo: `bilstm/.venv/bin/python bilstm/entrenar.py corrida --help`.

## Pruebas

```bash
bilstm/.venv/bin/python -m unittest discover -s bilstm/tests
```

## Historia

Los scripts de los experimentos de octubre de 2026 (unificación de datasets, depuración, series de política, longitud, titulares, prueba externa…) y sus informes se retiraron el 10 de noviembre de 2026. Están en el historial de Git, commit `d4ece74`.
