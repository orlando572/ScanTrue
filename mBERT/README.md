# mBERT de ScanTrue

Esta rama conserva el **checkpoint seleccionado** del último entrenamiento mBERT, el tokenizador, los scripts de preparación y entrenamiento, las métricas y la documentación. No contiene noticias ni datasets. Los resultados de las otras corridas se resumen en `PASO_4_RESUMEN.json`; sus pesos y checkpoints por época permanecen fuera de GitHub.

## Modelo publicado

- Base: `google-bert/bert-base-multilingual-cased`, revisión `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`.
- Corrida: `BILSTM_ES_main_len512_seed43_20261008-175737_516f4097`.
- Entrada: noticia completa como **una sola secuencia**, título incluido una sola vez cuando exista; máximo 512 tokens.
- Etiquetas: `0=REAL`, `1=FALSA`; umbral FALSA `0,5`.
- El archivo `model.safetensors` se distribuye mediante **Git LFS**. Instalar Git LFS antes de clonar o ejecutar `git lfs pull` después de clonar.

Desde la raíz del repositorio, una prueba manual en PowerShell:

```powershell
.\mBERT\.venv\Scripts\python.exe .\mBERT\inferir_bilstm_mbert.py --titulo "Titular" --cuerpo "Cuerpo de la noticia."
```

También se admite `--texto "Titular Cuerpo..."` o `--archivo-texto noticia.txt`. La salida es una clasificación textual experimental, **no una verificación factual**. La evaluación externa retrospectiva dio F1 macro `0,6001` en 569 casos, con 150 noticias reales marcadas falsas. Véanse `final_test_step7/MODELO_NUEVO_TARJETA.md` y `INFORME_TECNICO_ENTRENAMIENTOS_MBERT.md` para límites y resultados.

## Reproducción del entrenamiento

El código de preparación (`step1_*`, `step2_*`, `step3_*`) y `train_bilstm_step4.py` está incluido. Para entrenar de nuevo se requieren por separado los CSV originales y los manifiestos/datos procesados derivados; **no están en esta rama**. `download_phase_e_model.py` permite obtener los pesos base de la revisión registrada una vez que el tokenizador esté disponible. El entrenamiento original utilizó Python 3.14.7, PyTorch 2.13.0+cu130, Transformers 5.19.0, Datasets 5.1.0, Accelerate 1.15.0, scikit-learn 1.9.1, CUDA 13 y una RTX 5060 Laptop de 8 GB. `requirements.txt` enumera las bibliotecas de aplicación; PyTorch con CUDA debe instalarse desde el índice oficial de PyTorch correspondiente.

Los JSON históricos conservan rutas absolutas del equipo original. `inferir_bilstm_mbert.py` resuelve el modelo y el tokenizador dentro del clon y verifica sus SHA-256 antes de inferir. Los scripts de entrenamiento esperan la estructura de datos local descrita en `PLAN_REENTRENAMIENTO_BILSTM_20261008.md`.
