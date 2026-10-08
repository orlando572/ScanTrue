# Experimentos separados con embeddings fastText preentrenados

Se entrenaron BiLSTM nuevos con embeddings de **300 dimensiones**. Ningún
archivo del modelo principal de embeddings aleatorios de **128 dimensiones**
fue modificado. Las salidas están en `datasets/modelos_preentrenados/`; los
vectores descargados están en `datasets/embeddings_preentrenados/`. Ambas
carpetas quedan ignoradas por Git.

## Fuentes de los vectores

| Nombre | Origen oficial | Archivo local | Tamaño | SHA-256 |
| --- | --- | --- | ---: | --- |
| `fasttext_cc` | [fastText Common Crawl + Wikipedia](https://fasttext.cc/docs/en/crawl-vectors.html) | `cc.es.300.vec.gz` | 1.285.580.896 bytes | `116915c965346a0e3670b0e703e15e3526f31f1d216088eb3b30fc8f94982b82` |
| `fasttext_wiki` | [fastText Wikipedia](https://fasttext.cc/docs/en/pretrained-vectors.html) | `wiki.es.vec` | 2.594.302.560 bytes | `cf2e9a1976055a18ad358fb0331bc5f9b2e8541d6d4903b562a63b60f3ae392e` |

`entrenar.py` lee los vectores en streaming y carga solo las palabras del
vocabulario construido con la partición de entrenamiento. Las palabras sin
vector conservan una inicialización aleatoria. Los embeddings se ajustan
durante el entrenamiento. Se usan las mismas particiones, arquitectura BiLSTM,
optimizador y selección por F1 macro de validación que en el modelo principal;
solo cambia la inicialización y dimensión de embeddings. Se entrenó con
semillas 42, 43 y 44; el conjunto de prueba no se lee durante el entrenamiento.

La cobertura del vocabulario fue **93,3 %** para `fasttext_cc` y **94,0 %**
para `fasttext_wiki` con noticias completas; **96,9 %** y **97,3 %**,
respectivamente, con titulares. Son porcentajes de tipos de palabra, no de
ocurrencias.

## Noticias completas, máximo 192 tokens

| Inicialización | F1 macro validación s42 / s43 / s44 | Media ± desviación |
| --- | --- | ---: |
| Aleatoria 128, referencia | 64,96 / 65,98 / 62,85 % | 64,60 ± 1,59 % |
| Aleatoria 300, control s42 | 63,93 % | Una semilla |
| fastText Wikipedia 300 | 62,89 / 68,28 / 67,64 % | 66,27 ± 2,95 % |
| **fastText Common Crawl 300** | **69,34 / 71,34 / 70,07 %** | **70,25 ± 1,02 %** |

Se eligió `fasttext_cc_s43` por su F1 de validación para la comparación en
prueba. En las **807 noticias de prueba**, alcanzó **64,73 % de F1 macro**, **64,81 %
de exactitud** y **73,75 % de recall de «falsa»**. El modelo principal de 128
dimensiones había obtenido **61,45 %**, **61,46 %** y **67,19 %**, respectivamente.
El checkpoint `fasttext_cc_s42`, evaluado antes de completar las tres semillas,
obtuvo 64,31 % de F1 macro en ese mismo conjunto; esa consulta previa hace
exploratoria la comparación.

Por fuente, el candidato `fasttext_cc_s43` logró **56,53 % de F1 macro en
FakeDeS** frente a **55,66 %** del principal. En FalleDesinfo ES, con solo
33 casos, **no detectó ninguna de las 11 noticias falsas**. La mejora general
no demuestra fiabilidad homogénea ni justifica sustituir el modelo principal.

Checkpoint escogido:
`datasets/modelos_preentrenados/noticias_192/fasttext_cc_s43/mejor_modelo.pt`.

## Solo titulares, máximo 64 tokens

| Inicialización | F1 macro validación s42 / s43 / s44 | Media ± desviación |
| --- | --- | ---: |
| Aleatoria 128, referencia s42 | 53,01 % | Una semilla |
| Aleatoria 300, control s42 | 49,80 % | Una semilla |
| fastText Common Crawl 300 | 46,89 / 51,70 / 53,44 % | 50,68 ± 3,39 % |
| **fastText Wikipedia 300** | **52,58 / 53,28 / 60,77 %** | **55,54 ± 4,54 %** |

Se eligió `fasttext_wiki_s44` por validación. En los **675 titulares de prueba**,
obtuvo **55,75 % de F1 macro** y **59,26 % de exactitud**, frente a **53,22 %**
y **55,41 %** del BiLSTM de titulares de 128 dimensiones. Sin embargo, su
recall de «falsa» fue **37,10 %** frente a **40,28 %**: deja escapar más
titulares falsos. Además, varía bastante entre semillas; esta mejora es
exploratoria y requiere otra prueba independiente.

Checkpoint escogido:
`datasets/modelos_preentrenados/titulares/fasttext_wiki_s44/mejor_modelo.pt`.

## Reproducir y probar

Desde la raíz del repositorio, con `bilstm/.venv` y PyTorch CUDA instalados:

```bash
bilstm/.venv/bin/python bilstm/preentrenados/entrenar.py \
  --input datasets/experimentos_bilstm/sin_politica \
  --output datasets/modelos_preentrenados/noticias_192/nuevo_experimento \
  --embeddings datasets/embeddings_preentrenados/cc.es.300.vec.gz \
  --source fasttext_cc --max-len 192 --seed 42 --device cuda
```

Para titulares, usa `datasets/experimentos_titulares/sin_politica` como
`--input`, `wiki.es.vec` como `--embeddings`, `--source fasttext_wiki` y
`--max-len 64`. Cada ejecución necesita una carpeta `--output` nueva.

El checkpoint es compatible con el probador existente. Ejemplo para noticia
completa:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py \
  --modelo datasets/modelos_preentrenados/noticias_192/fasttext_cc_s43/mejor_modelo.pt \
  --referencia datasets/experimentos_bilstm/sin_politica \
  --texto 'Pega aquí el titular y el cuerpo de la noticia' --device cuda
```

Para el modelo de titulares, cambia `--modelo` a
`datasets/modelos_preentrenados/titulares/fasttext_wiki_s44/mejor_modelo.pt`,
`--referencia` a `datasets/experimentos_titulares/sin_politica` y pasa solo el
titular. Las probabilidades de ambos modelos son puntuaciones de clasificación,
no verificaciones de hechos.

Los JSON `resultados.json`, `config.json`, `historial.json` y
`evaluacion_prueba.json` de cada carpeta guardan los valores completos.
El conjunto de prueba y los casos externos ya han sido consultados en otros
experimentos del proyecto; para estimar el rendimiento final debe reservarse
una fuente nueva que no participe en ninguna decisión de entrenamiento.
