# Comparación inicial del BiLSTM sin predominio político

## Objetivo y preparación

La recomendación inicial es **entrenar con noticias españolas no políticas** y
usar las noticias políticas solo si demuestran una mejora en fuentes externas.
Para comprobarlo se prepararon dos variantes con `preparar_experimentos.py`:

| Variante | Entrenamiento | Noticias políticas | Validación | Prueba |
| --- | ---: | ---: | ---: | ---: |
| `sin_politica` | 1834 | 0 | 294 | 807 |
| `politica_25` | 2445 | 611 (24,99 %) | 294 | 807 |

Las dos variantes tienen exactamente los mismos archivos de validación y
prueba. Los 611 ejemplos políticos se seleccionan con semilla 42, manteniendo
aproximadamente la proporción de clases del resto del entrenamiento. Se
comprueba que los grupos de textos duplicados no crucen particiones. La
validación procede de Spanish Fake News Corpus v1 y la prueba reúne FakeDeS,
PolyglotFakeFacts, Spanish Fake and Real News de Acosta y FalleDesinfo_ES.

Se entrenó la misma arquitectura BiLSTM en ambos casos: vocabulario máximo
de 30 000 palabras aprendido solo de entrenamiento, embeddings de 128,
estado oculto de 64 por dirección, dropout 0,3, secuencias de hasta 192 tokens,
AdamW con tasa 0,001, pesos de clase, lote de 32 y semilla 42. Se escoge la
época con mejor F1 macro en validación y se evalúa la prueba una sola vez.
Se usó la GPU con PyTorch 2.14.1+cu130 y CUDA 13.0. La etiqueta **0 significa
falsa** y la **1, real**; precisión, recall y F1 de «falsa» tratan esa clase
como positiva.

## Resultados de la prueba común

| Variante | Mejor época | Exactitud | Precisión falsa | Recall falsa | F1 falsa | F1 macro |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `sin_politica` | 5 | 60,35 % | 56,64 % | 68,24 % | 61,90 % | 60,28 % |
| `politica_25` | 7 | 58,74 % | 55,69 % | 61,68 % | 58,53 % | 58,74 % |

| Fuente de prueba | N | F1 macro sin política | F1 macro política 25 % |
| --- | ---: | ---: | ---: |
| FakeDeS | 572 | 54,97 % | 52,30 % |
| PolyglotFakeFacts | 142 | 79,21 % | 79,03 % |
| Acosta | 60 | 78,28 % | 78,28 % |
| FalleDesinfo_ES | 33 | 30,05 % | 36,60 % |

**Recomendación provisional:** usar `sin_politica` como referencia para el
siguiente ciclo de mejora. Incluir el 25 % de noticias políticas no mejoró la
prueba común ni FakeDeS, que concentra 572 de las 807 noticias de prueba.
FalleDesinfo_ES mejoró en F1 macro, pero tiene solo 33 registros y su F1 para
la clase falsa cayó de 25,81 % a 17,39 %. Ninguno de los dos modelos tiene aún
una calidad suficiente para uso real sin más datos y evaluación.

Es un experimento con una sola semilla y una validación de una sola fuente.
La diferencia observada no demuestra que cualquier noticia política perjudique
al modelo. Para confirmar la decisión conviene ampliar las fuentes no
políticas, repetir con varias semillas y evaluar por tema y por fuente.
También hay que revisar manualmente posibles noticias muy parecidas entre
fuentes: el filtro actual detecta duplicados normalizados, pero no paráfrasis.

## Reproducción

Desde la raíz del proyecto, con las dependencias de `bilstm/requirements.txt`
instaladas en `bilstm/.venv`:

```bash
bilstm/.venv/bin/python bilstm/preparar_experimentos.py
bilstm/.venv/bin/python bilstm/entrenar_baseline.py --variant sin_politica
bilstm/.venv/bin/python bilstm/entrenar_baseline.py --variant politica_25
bilstm/.venv/bin/python -m unittest discover -s bilstm -p 'test_*.py' -v
```

Las particiones, `manifest.json`, modelos `modelo.pt` y resultados detallados
`metricas.json` se guardan en `datasets/experimentos_bilstm/` y están
ignorados por Git. No se modifica `README.md` de la raíz.
