# Preparación de datos para el BiLSTM

El preparador lee los originales de `datasets/` y escribe cuatro archivos en
`datasets/estandarizados/`. Los originales no cambian y las salidas están
ignoradas por Git.

## Entorno comprobado

- Python 3.14.4; PyTorch 2.14.1+cu130; runtime CUDA 13.0.
- NVIDIA GeForce RTX 3050 6 GB, controlador 595.91.07; una operación CUDA de
  PyTorch se ejecutó correctamente en este equipo.
- pandas 3.0.6, NumPy 2.5.2, scikit-learn 1.9.1 y openpyxl 3.1.5.
- La preparación de CSV y XLSX usa CPU. La GPU se usa al entrenar el modelo.

## Ejecución

Desde la raíz del proyecto:

```bash
bilstm/.venv/bin/python -m unittest discover -s bilstm -p 'test_preparar_datasets.py' -v
bilstm/.venv/bin/python bilstm/preparar_datasets.py
```

El programa acepta `--input` y `--output` para cambiar las rutas. En Windows,
usa el intérprete de `bilstm/.venv/Scripts/python.exe`.

## Salidas

- `directos.csv`: todos los registros de las tres fuentes de
  `servir_directamente`, con columnas comunes.
- `no_directos.csv`: todos los registros legibles de `no_directamente`, con su
  tarea, etiqueta original y motivo de inclusión o exclusión. No convierte
  fiabilidad, sátira, afirmaciones ni verificaciones a verdad/falsedad.
- `unificado.csv`: noticias binarias aptas de ambas carpetas, con
  `particion` igual a `entrenamiento`, `validacion` o `prueba`.
- `reporte.json`: recuentos por fuente, partición, etiqueta y duplicados.

La columna `etiqueta` vale **0 para falsa** y **1 para real**. `dataset`,
`fuente`, `url` y otros metadatos sirven para auditoría; no deben introducirse
como características del modelo. `texto` es el campo de entrada y puede unir
titular y cuerpo cuando el titular no está ya al inicio.

Se preservan las particiones originales de Spanish Fake News Corpus v1,
Spanish Fake and Real News, FakeDeS y PolyglotFakeFacts. FalleDesinfo_ES se
reserva como prueba externa: T1 se mapea a falsa y T2/T3 a real. Las noticias políticas se dividen 80/10/10
agrupando titulares idénticos. El conjunto unificado retira textos, URL y
titulares repetidos entre particiones, da prioridad a la prueba y aparta
conflictos de etiquetas. USMSC queda en la tabla no directa, pero se excluye
del unificado porque reúne fuentes que ya están presentes. FakeCovid,
FactOReS, Zenodo, RUN-AS y FLARES conservan sus etiquetas originales y quedan
fuera del entrenamiento binario por diferencia de tarea o de unidad de texto.

**Límites de la evaluación:** el corpus político domina el tamaño del
unificado y parte de sus noticias falsas se construyó modificando noticias
reales. Por ello, informa las métricas también por fuente y presta especial
atención a FakeDeS como prueba externa. El preparador retira coincidencias
exactas normalizadas; las paráfrasis aún pueden requerir una revisión manual.
El vocabulario del BiLSTM se aprende solo de la partición de entrenamiento;
las secuencias se truncan a 192 tokens y se rellenan por lote. La comparación
de entrenamiento sin política y con política limitada al 25 % se describe en
`bilstm/EXPERIMENTOS.md`.
