# Código común a BiLSTM y mBERT

Construye el conjunto común `datasets/comun_v1/`, lo lee por pliegues y evalúa las predicciones de cualquier modelo con las mismas métricas. Plan: [docs/mejora_modelos/01_PLAN_COMUN.md](../docs/mejora_modelos/01_PLAN_COMUN.md).

```
datos_comunes/
├── construir_comun.py   Construye datasets/comun_v1/ desde datasets/unificado/
├── limpieza.py          Limpieza de marcas de medio y detector de idioma
├── grupos.py            Agrupa copias y noticias relacionadas para que no crucen particiones
├── comun.py             Lee el conjunto y arma pliegues y validación interna
├── evaluar_comun.py     Métricas por artículo, bootstrap, temperatura y niveles de la extensión
├── referencias.py       Referencias: solo longitud y TF-IDF de caracteres
├── calibrar_conjunto.py Calibración conjunta: temperaturas, combinación BiLSTM + mBERT y niveles
└── tests/               Pruebas
```

## Uso

```bash
bilstm/.venv/bin/python datos_comunes/construir_comun.py --salida datasets/comun_v1 --sobrescribir
```
```bash
bilstm/.venv/bin/python datos_comunes/referencias.py --salida datasets/comun_v1_corridas/referencias
```
```bash
bilstm/.venv/bin/python datos_comunes/evaluar_comun.py --predicciones RUTA/predicciones.csv --salida RUTA/evaluacion
```
```bash
bilstm/.venv/bin/python datos_comunes/calibrar_conjunto.py --sobrescribir
```
```bash
bilstm/.venv/bin/python -m unittest discover -s datos_comunes/tests
```

`calibrar_conjunto.py` lee las predicciones fuera de pliegue de los dos modelos finales y escribe `datasets/comun_v1_corridas/calibracion/`. Decisiones y cifras en [docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md](../docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md).

`construir_comun.py` usa el tokenizador de `bilstm/modelo.py`, para que el mínimo de 100 tokens coincida con el del backend.
