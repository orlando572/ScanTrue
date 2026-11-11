# Fase C — decisiones y particiones congeladas

**Fecha:** 7 de octubre de 2026. **Estado:** particiones v1 congeladas y verificadas. No se ha entrenado ningún modelo. La fase D medirá tokens y preparará las líneas base.

## Archivos reproducibles

- [manifest.json](../datasets/processed/phase_c_seed42_v1/manifest.json): semilla, hash SHA-256 del JSONL de fase B, tamaños, soporte por clase, reglas y limitaciones.
- [decisions.csv](../datasets/processed/phase_c_seed42_v1/decisions.csv): los 48 772 IDs con corpus, split original, partición final, motivo y componente de similitud. **Ninguna fila del original se borró**; `excluded` y `es_test_quarantine` conservan la trazabilidad.
- Archivos `*_ids.txt` en [phase_c_seed42_v1](../datasets/processed/phase_c_seed42_v1): IDs de cada partición activa y de la cuarentena. Son los manifiestos que deberán leer los experimentos, siempre cruzados con el SHA-256 del origen.
- [verification.json](../datasets/processed/phase_c_seed42_v1/verification.json): comprobación independiente de conteos, IDs, procedencia y grupos que cruzan particiones.
- [create_phase_c.py](create_phase_c.py) y [verify_phase_c.py](verify_phase_c.py): scripts. El generador rehúsa sobrescribir `phase_c_seed42_v1`; una revisión futura debe usar otro directorio/versionado y registrarse como una decisión nueva. Cada entrenamiento seguirá teniendo su carpeta de ejecución exclusiva.

## Decisiones adoptadas

1. **Español v1:** mantener `train.xlsx` para `es_train` y `development.xlsx` para `es_validation`. Se excluyen 5 registros de desarrollo conectados con entrenamiento (4 por texto exacto y 1 por titular casi idéntico), 1 duplicado dentro del propio desarrollo, 4 textos cortos y 5 con URL social en entrenamiento. Se conservan 667/289 registros. No se reasignan filas de desarrollo a entrenamiento.
2. **Español v2:** reservarlo para prueba. Se excluyen de la prueba principal 4 registros conectados con v1 por titular o URL, aunque sus cuerpos no sean exactamente iguales. Otros **117** quedan en `es_test_quarantine`, sin uso para selección ni métrica principal: 88 tienen como motivo principal `AFPFactual` con tipo sin confirmar, 16 están ligados a plataformas sociales, 10 a fuentes de verificación, 2 tienen menos de 50 palabras y 1 tiene posible marca de etiqueta. **Las 90 filas de `AFPFactual` están en cuarentena**; dos se registran bajo el motivo de longitud, que tiene prioridad en el archivo de decisiones. La cuarentena es conservadora: no afirma que todas esas filas sean publicaciones sociales ni que identifique exactamente las 90 descritas por los autores.
3. **Prueba española principal:** `es_test_main` contiene **451** artículos de v2: 284 reales y 167 falsos. Esta prueba queda **congelada** para evaluación final; no debe servir para elegir longitud, umbral, época o mezcla de idiomas. Está desbalanceada tras las exclusiones; reportar F1 de FALSA junto con precisión, recall, F1 macro, matriz de confusión y soporte por clase.
4. **Polyglot:** reservar 750 originales españoles elegibles en `es_test_polyglot_stress`, sin usar ninguno para entrenar o validar. Los 582 originales ingleses quedan fuera del experimento inicial; había señales de idioma erróneo y sesgo de fuente. La prueba española Polyglot **no es una estimación externa balanceada**: casi todos sus reales elegibles proceden de una única fuente. Su puntuación será solo una prueba de estrés, separada de la prueba principal. No se ha encontrado todavía un corpus externo español independiente con etiquetas y fuentes suficientemente comparables; esa limitación se conservará en el informe final.
5. **ISOT:** excluir cuerpos vacíos, textos de menos de 50 palabras, posibles marcas de etiqueta y duplicados. Agrupar versiones exactas o parecidas y escoger un representante por grupo. Dividir con semilla 42 y estratificación aproximada por clase a nivel de grupo: **29 949** en `en_train` y **7 488** en `en_validation`. El origen Reuters de gran parte de los reales sigue siendo un sesgo importante: la validación inglesa sirve para escoger checkpoints de E2, no para afirmar generalización factual.
6. **Pérez-Rosas:** reservar **949** artículos elegibles como `en_test_perez_rosas`, prueba inglesa externa. Los 8 pares de titulares semejantes con etiquetas opuestas permanecen juntos en esta prueba, sin cambiar etiquetas; varios son ejemplos deliberados de afirmaciones distintas. No entran en entrenamiento inglés.

| Partición | REAL | FALSA | Total | Uso |
| --- | ---: | ---: | ---: | --- |
| `es_train` | 338 | 329 | 667 | E1, E3, ajuste español E4 |
| `es_validation` | 150 | 139 | 289 | Selección de E1, E3, E4 y umbral español |
| `es_test_main` | 284 | 167 | 451 | Prueba española final, una vez fijado el modelo |
| `es_test_polyglot_stress` | 473 | 277 | 750 | Estrés externo con sesgo de fuente declarado |
| `en_train` | 16 535 | 13 414 | 29 949 | E2, E3 y primera etapa E4 |
| `en_validation` | 4 134 | 3 354 | 7 488 | Selección de E2, sin etiquetas españolas |
| `en_test_perez_rosas` | 490 | 459 | 949 | Prueba inglesa secundaria |

Además, 117 registros están en cuarentena y 8 112 excluidos de las particiones activas. `decisions.csv` contiene el motivo individual. Las exclusiones no se usan como ejemplos negativos ni como «datos sin etiqueta».

## Regla de agrupación y comprobación de fuga

Antes de dividir, se construyeron componentes conectados por: cuerpo normalizado exactamente igual, URL de artículo normalizada igual (se ignoran URL de página de inicio), titular normalizado igual con al menos 6 palabras, o un par de titulares candidatos detectado en fase B. Una componente no puede ocupar dos particiones activas. En ISOT la división se hizo **después** de agrupar y escoger representante; con semilla 42 se asignó aproximadamente el 20 % de componentes de cada clase a validación.

La verificación independiente revisó el SHA-256 del origen, los 48 772 IDs una sola vez, la correspondencia de cada archivo de IDs, el corpus y etiqueta de cada fila y el cruce de componentes: **0 componentes activos cruzan particiones**. También se revisaron titulares normalizados idénticos entre particiones activas, sin cruces observados.

**Límite importante:** esta prueba no detecta exhaustivamente paráfrasis del mismo evento ni equivalencias inglés↔español. La atribución de tipo social/artículo en v2 carece de una columna fiable. El uso de prueba v2 como evaluación de otro período debe matizarse: se hallaron artículos antiguos repetidos y se retiraron los cuatro cruces identificados. Si aparecen nuevos cruces, se debe versionar una nueva partición y no modificar estos manifiestos.

## Reglas para los experimentos posteriores

- E1: `es_train` → `es_validation`; E2: `en_train` → `en_validation`; E3: unir únicamente los **entrenamientos** inglés y español y validar con `es_validation`; E4: partir de un checkpoint E2 en una ejecución nueva y ajustar con `es_train`, validando con `es_validation`.
- El checkpoint de E2 se decide exclusivamente con `en_validation`. Ningún ejemplo de `es_test_main`, `es_test_polyglot_stress`, `en_test_perez_rosas` o `es_test_quarantine` entra en entrenamiento o en selección de hiperparámetros.
- El modelo leerá solo titular/cuerpo como entrada; fuente, URL, split, etiqueta y flags son metadatos de auditoría. En fase D se concretará el separador `[SEP]`, el tratamiento de datelines Reuters y las longitudes **128, 192, 256** (y 512 condicional) sin alterar este manifiesto de IDs.
- Cada longitud, semilla, combinación y fase de ajuste será una **ejecución separada**, con directorio exclusivo y sin sobrescribir checkpoints ni métricas previas.
