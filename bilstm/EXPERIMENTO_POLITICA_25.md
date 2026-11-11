# Experimento: 0 %, 25 % y 50 % de noticias políticas

## Diseño

Se compararon tres conjuntos de entrenamiento **sin modificar los datos ni checkpoints anteriores**. Todos los modelos son BiLSTM con vectores **fastText CC español de 300 dimensiones**, máximo **192 tokens**, lote de 32, hasta 20 épocas y parada temprana tras cuatro épocas sin mejora. Se entrenaron con **CUDA** y semillas 42, 43 y 44. Cada checkpoint se eligió por F1 macro en la misma validación de 170 noticias.

| Conjunto | Entrenamiento | Noticias políticas añadidas | Proporción |
| --- | ---: | ---: | ---: |
| `pequeno_mejorado` | 3 066 | 0 | 0 % de la fuente política explícita |
| `pequeno_politica_25` | 4 088 | 1 022 | 25 % |
| `grande_balanceado` | 6 132 | 3 066 | 50 % |

Las 1 022 noticias políticas del conjunto intermedio también pertenecen al grande. El conjunto pequeño mantiene 769 noticias de Spanish Fake News Corpus v1, 614 de PolyglotFakeFacts y 1 683 textos residuales USMSC/Edds. Es posible que algunas de estas fuentes traten política; los porcentajes indican la **fuente política explícita**, no una clasificación temática de todos los textos. Los tres conjuntos usan exactamente las mismas particiones de validación (170), prueba interna (179) y fuentes reservadas (606), sin grupos de duplicados cruzados.

## Resultados de las tres semillas

El F1 indicado es **macro**, promedio de la clase falsa y la real. FP significa noticia **real** predicha como falsa. La tasa FP divide FP entre el total de noticias reales. Las cifras con ± son media y desviación poblacional entre las tres semillas; no representan un intervalo de confianza ni variación entre particiones.

| Política | F1 validación, media | F1 prueba interna (179) | FP internos / 110 reales | F1 reservadas (606) | FP reservados / 307 reales | Recall falsa reservado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 % | 0,728 | **0,749 ± 0,024** | **25,0; 22,7 %** | **0,587 ± 0,014** | 161,7; 52,7 % | **71,6 %** |
| 25 % | **0,733** | 0,721 ± 0,019 | 29,7; 27,0 % | 0,548 ± 0,008 | 176,0; 57,3 % | 68,9 % |
| 50 % | 0,723 | 0,721 ± 0,009 | 33,0; 30,0 % | 0,583 ± 0,005 | **149,7; 48,8 %** | 66,0 % |

| Política | Semilla | F1 interno | FP internos | F1 reservado | FP reservados |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 % | 42 | 0,774 | 23 | 0,603 | 164 |
| 0 % | 43 | 0,717 | 29 | 0,568 | 169 |
| 0 % | 44 | 0,755 | 23 | 0,591 | 152 |
| 25 % | 42 | 0,722 | 34 | 0,537 | 196 |
| 25 % | 43 | 0,744 | 31 | 0,552 | 171 |
| 25 % | 44 | 0,697 | 24 | 0,555 | 161 |
| 50 % | 42 | 0,728 | 34 | 0,587 | 158 |
| 50 % | 43 | 0,727 | 33 | 0,575 | 154 |
| 50 % | 44 | 0,708 | 32 | 0,587 | 137 |

## Falsos positivos por fuente

Valores medios de las tres semillas. El desglose completo, incluidas matrices de confusión, F1, precisión, recall y tasas por semilla, está en `datasets/experimentos_balanceados/serie_politica/comparacion.json`.

| Prueba y fuente | Reales | FP 0 % | FP 25 % | FP 50 % |
| --- | ---: | ---: | ---: | ---: |
| Interna: PolyglotFakeFacts | 58 | 7,7 | 8,0 | 8,0 |
| Interna: Spanish Fake News Corpus v1 | 52 | **17,3** | 21,7 | 25,0 |
| Reservada: FakeDeS | 284 | 153,7 | 168,3 | **144,3** |
| Reservada: FalleDesinfo | 22 | 7,0 | 6,7 | **4,3** |
| Reservada: Spanish Fake News Corpus v1 | 1 | 1,0 | 1,0 | 1,0 |

La última fila tiene **una sola noticia real**; su tasa por fuente no es útil para decidir. La prueba reservada está dominada por FakeDeS (570 de 606 filas).

## Interpretación y siguiente decisión

**El 25 % no mejoró este experimento.** Aunque logró el mayor F1 medio de validación, bajó el F1 de las dos pruebas y elevó los falsos positivos respecto al 0 %. El 50 % tampoco superó el F1 del 0 %, pero produjo menos falsos positivos en las fuentes reservadas y menos recall de falsas: hay un compromiso entre ambos errores.

Para el objetivo de F1 macro, el conjunto pequeño sin la fuente política explícita es el candidato actual. Su semilla 42 tuvo el mayor F1 individual (0,774 interno; 0,603 reservado), pero elegirla por la prueba reservada repetiría el sesgo de selección. **No se promueve ningún checkpoint nuevo** con estos datos.

La partición de 606 noticias se ha consultado en varias rondas; ahora funciona como diagnóstico exploratorio y **no es una prueba externa inédita**. Para confirmar cualquier mejora antes de desplegar, hace falta un corpus nuevo en español con etiquetas de veracidad comparables, procedencia verificable y ausencia de duplicados o noticias del mismo evento frente al entrenamiento y las pruebas actuales. Se debe fijar el checkpoint y el umbral **antes** de medir ese corpus y reportar F1, recall, precisión y FP por fuente. Un corpus que solo marque noticias falsas no permitiría estimar falsos positivos ni F1 binario.

**Seguimiento:** `bilstm/PRUEBA_EXTERNA_XFACT.md` documenta una prueba nueva con 594 afirmaciones españolas verificadas. El 25 % tampoco mejoró su F1, pero son afirmaciones de 4–35 tokens de un solo sitio, no artículos completos; por tanto sigue pendiente una confirmación externa del objetivo principal.

## Archivos y reproducción

- `bilstm/preparar_politica_25.py` crea `datasets/experimentos_balanceados/pequeno_politica_25/` sin sobrescribirlo.
- `bilstm/entrenar_serie_politica.py` completa las semillas faltantes en `datasets/modelos_balanceados/serie_politica/`; reutiliza los checkpoints de semilla 42 previos para 0 % y 50 %.
- `bilstm/evaluar_serie_politica.py` evalúa los nueve checkpoints en CUDA y guarda el JSON de comparación.

Desde la raíz del proyecto, en un entorno con GPU CUDA disponible:

```bash
bilstm/.venv/bin/python bilstm/preparar_politica_25.py
bilstm/.venv/bin/python bilstm/entrenar_serie_politica.py
bilstm/.venv/bin/python bilstm/evaluar_serie_politica.py
```

Los dos primeros comandos protegen las salidas existentes; no los ejecutes de nuevo para regenerarlas sin elegir una carpeta nueva. El evaluador sí puede recalcular su propio reporte.
