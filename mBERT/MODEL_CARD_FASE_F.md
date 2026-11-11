# Tarjeta del candidato mBERT — evaluación de fase F

**Estado: experimental; no apto para despliegue.** Esta tarjeta describe el checkpoint fijado antes de abrir las pruebas, no un modelo elegido después de verlas.

## Modelo y uso previsto

- Base: `google-bert/bert-base-multilingual-cased`, revisión `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`.
- Tarea: clasificar textos periodísticos como `0 = REAL` o `1 = FALSA`. Entrada: titular + cuerpo, o solo cuerpo si falta titular; máximo 256 tokens. Umbral fijo 0,5.
- Checkpoint: [E1 semilla 44](runs/E1_len256_seed44_20261007-202946_bda20c1f/best_model), SHA-256 de `model.safetensors`: `7e6a88893c10f0d9ea89ec6b9347e00f872f140ce2752b7fa00011ccb634ff5c`.
- Entrenamiento: 667 artículos españoles; validación: 289; 3 épocas, tasa `2e-5`, PyTorch/CUDA, `bf16`. Este candidato se eligió por F1 de FALSA en validación española. Las otras semillas, longitudes y combinaciones de inglés están preservadas en ejecuciones separadas.

## Evaluación externa

En `es_test_main` (451 noticias, 284 reales y 167 falsas), F1 de FALSA **0,535**, precisión **0,368**, recall **0,982**, F1 macro **0,274**, exactitud **0,368**, AP **0,421** y Brier **0,424**. Matriz de confusión `[[2, 282], [3, 164]]`: **282 noticias reales se marcaron falsas**. En la prueba española Polyglot de estrés, F1 **0,527**; en la prueba inglesa Pérez‑Rosas, F1 **0,653**. Véase [el informe completo](FASE_F_EVALUACION.md) y [las métricas guardadas](evaluations/phase_f_20261007_v1/results.csv).

## Límites y decisiones

El checkpoint casi siempre predice FALSA en la prueba española externa y sus probabilidades no están calibradas para uso público. El tamaño del entrenamiento español es pequeño; las fuentes, los temas y los métodos de etiquetado difieren entre corpus. Polyglot tiene una asociación extrema entre fuente y clase. La evaluación no demuestra verificación factual: el modelo no consulta evidencia, contexto ni cambios temporales. **No usar para moderación automática, acusaciones sobre medios o personas, ni como veredicto de veracidad.** Se conserva para reproducibilidad e investigación. Antes de cualquier nueva versión, revisar procedencia y etiquetas, ampliar diversidad de fuentes, probar validación por evento/fuente y reservar una nueva prueba externa.
