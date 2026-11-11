# Probar noticias externas con el BiLSTM

Hay dos pruebas distintas. Una noticia individual permite ver una predicción;
un conjunto de noticias con etiquetas verificadas permite calcular métricas.
La salida del clasificador no verifica hechos ni constituye un porcentaje de
certeza de que una noticia sea falsa.

## 1. Una noticia nueva

Guarda el **texto completo** de una noticia en un archivo UTF-8 y ejecuta,
desde la raíz del proyecto:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py --archivo /ruta/noticia.txt
```

Por defecto se carga el modelo principal de 192 tokens. Para probar el
candidato de 512 tokens entrenado con la semilla 42:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py --archivo /ruta/noticia.txt --modelo datasets/experimentos_longitud/t512_s42/mejor_modelo.pt
```

La salida muestra `prediccion` (`falsa` o `real`), `prob_falsa`, cuántos tokens
tiene el texto y cuántos leyó el modelo. `prob_falsa` es la salida del modelo,
**no una probabilidad calibrada ni una verificación factual**. Si el texto
coincide exactamente con uno de los conjuntos anteriores, se indicará un
solapamiento. También puedes pasar una noticia breve mediante `--texto`, pero
un archivo evita problemas al citar textos largos en la terminal.

## 2. Evaluar un conjunto externo

Prepara un CSV UTF-8 con, al menos, estas columnas:

| Columna | Significado |
| --- | --- |
| `texto` | Texto de la noticia que verá el modelo. Obligatoria. |
| `etiqueta` | `0` si está verificada como falsa; `1` si está verificada como real. Necesaria para métricas. |
| `fuente` | Nombre del medio o conjunto de datos. Recomendada para métricas por fuente. |
| `titulo`, `url`, `id` | Opcionales; ayudan a revisar duplicados y resultados. |

Ejemplo de estructura, con textos de ejemplo que **no son noticias reales**:

```csv
id,fuente,texto,etiqueta
1,fuente_A,"Texto completo de una noticia falsa ya verificada",0
2,fuente_B,"Texto completo de una noticia real ya verificada",1
```

Ejecuta:

```bash
bilstm/.venv/bin/python bilstm/probar_externo.py --csv /ruta/noticias_externas.csv --modelo datasets/experimentos_longitud/t512_s42/mejor_modelo.pt --salida datasets/evaluaciones_externas/predicciones_512.csv
```

Se imprimirán exactitud, precisión, recall y F1 para la clase falsa, F1 macro,
matriz de confusión y métricas por fuente. El archivo de salida contiene la
predicción por fila para revisar errores. Si no hay columna `etiqueta`, se
generan predicciones, pero no métricas. Los textos idénticos a entrenamiento,
validación o prueba previa y los duplicados internos se marcan y se excluyen
del cálculo. El programa rechaza noticias externas idénticas con etiquetas
contradictorias.

## Qué cuenta como prueba externa válida

- Usa noticias en español con **etiquetas documentadas y comprobables**.
  Una noticia publicada por un medio no es automáticamente «real»; una
  afirmación desmentida no siempre equivale a un artículo completo falso.
- Reúne ambas clases y varias fuentes, temas y fechas. Registra de dónde viene
  cada noticia y cómo se determinó su etiqueta.
- No utilices noticias ya presentes en entrenamiento, validación o la prueba
  anterior. El script comprueba texto, URL y título exactos normalizados frente
  a entrenamiento, validación y prueba previa; las paráfrasis o
  republicaciones requieren revisión manual.
- Reúne el conjunto y fija sus etiquetas **antes de comparar modelos**. Para
  comparar 192 y 512 tokens, ejecuta ambos sobre exactamente el mismo CSV y
  observa tanto el resultado global como el de cada fuente.

Los modelos y las predicciones bajo `datasets/` están ignorados por Git. El
script no descarga noticias ni decide sus etiquetas: esas dos tareas deben
hacerse antes de la evaluación.
