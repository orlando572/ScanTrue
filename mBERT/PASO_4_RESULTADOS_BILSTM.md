# Paso 4: entrenamientos independientes con los datos BiLSTM

**Estado:** ejecuciones finalizadas y verificadas. La selección de configuración corresponde al paso 5; prueba y externa no se usaron.

Cada ejecución cargó desde cero el checkpoint base mBERT local, usó solo `text` como secuencia única y entrenó tres épocas con `2e-5`, decaimiento 0,01, calentamiento 10 %, lote efectivo 16 y BF16 en la RTX 5060 Laptop. Se guardaron los tres checkpoints, el mejor por F1 macro de validación (empate por época anterior), logs, configuración, hashes, memoria, tiempos y predicciones de validación por ID. Todos los checkpoints recargados reprodujeron la F1 seleccionada.

| Brazo | Tokens | Semillas | F1 macro media ± DE | Falsas alarmas media | Tiempo medio | Pico asignado por PyTorch |
|---|---:|---|---:|---:|---:|---:|
| main | 128 | 42, 43, 44 | 0.8829 ± 0.0127 | 8.240% | 162 s | 3.38 GB |
| main | 192 | 42, 43, 44 | 0.8921 ± 0.0212 | 8.240% | 163 s | 3.38 GB |
| main | 256 | 42, 43, 44 | 0.9117 ± 0.0134 | 6.742% | 163 s | 3.41 GB |
| main | 512 | 42, 43, 44 | 0.9220 ± 0.0143 | 4.494% | 445 s | 3.40 GB |
| no_usmsc | 128 | 42, 43, 44 | 0.8596 ± 0.0157 | 11.610% | 80 s | 3.38 GB |
| no_usmsc | 192 | 42, 43, 44 | 0.8761 ± 0.0054 | 7.865% | 67 s | 3.38 GB |
| no_usmsc | 256 | 42, 43, 44 | 0.8907 ± 0.0128 | 7.116% | 60 s | 3.41 GB |
| no_usmsc | 512 | 42, 43, 44 | 0.8985 ± 0.0270 | 5.243% | 131 s | 3.40 GB |

La ablación `no_usmsc` excluye solo los 1.647 ejemplos USMSC/Edds del entrenamiento: conserva 1.141 ejemplos; usa los mismos 132 de validación. No modifica la política de prueba. La comparación de configuraciones y la elección de un checkpoint concreto se harán en el paso 5 según el plan congelado.

El pico indicado es `torch.cuda.max_memory_allocated()`, no el uso total informado por el controlador de la GPU.

Las 24 corridas ocupan bastante espacio porque conservan los tres checkpoints con el estado del optimizador además del modelo elegido. Tras completar la matriz, la unidad D: tenía aproximadamente **83 GB libres**. Conviene tenerlo presente antes de lanzar bloques adicionales; no se borró ningún artefacto previo.

[Resumen completo en JSON](PASO_4_RESUMEN.json) · [Estado de la matriz](PASO_4_MATRIX_STATUS.json) · [Código de una ejecución](train_bilstm_step4.py) · [Ejecutor de la matriz](run_bilstm_step4_matrix.py)
