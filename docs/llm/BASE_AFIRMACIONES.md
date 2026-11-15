# Fase 3: base de afirmaciones ya verificadas

**Fecha:** 15 nov 2026. **Plan:** [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md), Fase 3 y 4.5 (Paso 2, D5).
**Decisión (tomada por el usuario tras la medición): la base reutiliza solo la coincidencia exacta** del texto normalizado. La búsqueda por similitud de trigramas queda apagada. Esto se aparta del Paso 2 del plan, que preveía una búsqueda por similitud con un umbral.

## 1. Qué hace

Antes de buscar en internet, cada afirmación extraída se busca en esta base. Si ya se verificó y no ha expirado, se reutiliza su veredicto con sus fuentes y se marca `origen: base_anterior`. Al terminar la verificación de un caso, sus afirmaciones se guardan.

- **Tabla:** `afirmaciones_verificadas`, creada en la migración 008. Las funciones `buscar_afirmacion_verificada` y `guardar_afirmacion_verificada` son de la migración [009](../../backend/db/migrations/009_afirmaciones_verificadas.sql).
- **Código:** [known_claims.py](../../backend/services/verification/known_claims.py) (`find_known_claim`, `save_known_claim`) y los métodos `find_verified_claims` y `save_verified_claim` del repositorio.
- **Normalización** (la misma al guardar y al buscar): minúsculas, sin tildes, sin signos de puntuación y con los espacios colapsados. «El 12 de marzo, Lima.» y «el 12 de MARZO lima» son la misma afirmación; «Lima» y «Quito» no.
- **Vigencia (D5):** 30 días; 7 si el veredicto fue `insuficiente`. La calcula la base al guardar y se renueva si se vuelve a guardar la misma afirmación.
- **Búsqueda por similitud:** la función SQL y `find_known_claim(threshold=…)` siguen disponibles, con comprobaciones de cifras y negación, pero `SIMILARITY_THRESHOLD` es `None`: apagada. Sin umbral, el repositorio envía 2,0 (ninguna similitud lo alcanza); un `null` no serviría, porque la función lo trataría como 0,3.

## 2. Regla para fijar el umbral (escrita antes de medir)

La preocupación principal era **reutilizar mal**: dos afirmaciones que difieren en un dato comparten casi todos sus trigramas, pero tienen veredictos distintos.

- **Comprobaciones además del umbral:** una coincidencia aproximada solo se acepta con **las mismas cifras** y **las mismas palabras de negación**. Una comprobación de nombres propios se añadiría solo si el umbral elegido resultaba **mayor que 0,90**.
- **Pares de medición:** positivos (la misma afirmación reescrita) y negativos difíciles (un solo hecho cambiado: cifra, entidad, hecho principal o contraria) generados por el LLM (Q8_0, temperatura 0) a partir de afirmaciones reales y etiquetados por construcción; negativos fáciles: afirmaciones de otros textos. Se descarta, y se cuenta, el par en que el LLM no hizo el cambio pedido.
- **Partición, antes de medir:** los 36 textos de origen ordenados por identificador y repartidos alternando entre **ajuste** y **control**.
- **Elección:** el menor umbral (0,30 a 0,95, de 0,05 en 0,05) con **0 coincidencias falsas** en los negativos del ajuste; confirmar en el control; la tasa de paráfrasis reutilizadas se informa pero **no decide**: se prefiere no reutilizar a reutilizar mal.

## 3. Resultados de la medición

**Los pares.** 172 afirmaciones reales (de 36 textos) generaron estos pares válidos: 122 de hecho distinto, 99 contrarias, 83 de entidad distinta, 8 de cifra distinta y 128 paráfrasis. Negativos con guardas: ajuste 3.555 (de ellos 148 difíciles: cifra 7, entidad 35, hecho 54, contraria 52) y control 3.737 (difíciles 164: cifra 1, entidad 48, hecho 68, contraria 47); el resto son fáciles.

**Un cambio posterior a escribir la regla.** La primera instrucción de paráfrasis («con otras palabras») devolvió el mismo texto en 150 de 172 casos y solo dejó 10 paráfrasis válidas. Se sustituyó por otra («sinónimos y una estructura de oración distinta», 128 válidas) **después** de ver ese fallo y el barrido de negativos. Solo afecta a la tasa de paráfrasis reutilizadas, que no decide nada.

**Coincidencias falsas** (negativos aceptados por el umbral y las comprobaciones; entre paréntesis, sin las comprobaciones):

| Umbral | Ajuste | Control |
| --- | --- | --- |
| 0,30 | 89 (148) | 116 (164) |
| 0,50 | 87 (146) | 109 (157) |
| 0,70 | 67 (126) | 74 (121) |
| 0,80 | 42 (101) | 45 (92) |
| 0,85 | 22 (81) | 28 (75) |
| 0,90 | 9 (66) | 9 (53) |
| 0,95 | **1** (49) | **3** (45) |

**Paráfrasis reutilizadas** (128 en total, con comprobaciones): 0,30 → 98 (77 %); 0,50 → 32 (25 %); 0,60 → 10 (8 %); 0,70 → 5 (4 %); 0,80 → 2 (2 %); 0,85 → 1 (1 %); 0,90 y 0,95 → 0. La similitud de las paráfrasis es: mínima 0,13, mediana 0,42, máxima 0,87. Las paráfrasis válidas conservan por construcción cifras y negación, así que las comprobaciones no rechazan ninguna.

**Resultado de la regla: no existe un umbral que cumpla.** Ninguno hasta 0,95 llega a 0 coincidencias falsas (el ajuste deja 1 a 0,95 y el control 3). Como el umbral resultante superaría 0,90, la regla añadía la comprobación de nombres propios: con ella siguen 5 coincidencias falsas a 0,90 y 1 a 0,95 en cada mitad. Y con 0,95 se reutiliza el 0 % de las paráfrasis.

**Por qué.** Lo que pasa los filtros son cambios reales de un solo dato, que comparten el 90–97 % de los trigramas con el original:

| Similitud | Original → cambiada |
| --- | --- |
| 0,97 | «…dijo que está **de acuerdo** con los comentarios del papa» → «…**en desacuerdo**…» |
| 0,96 | «…en **Florida**, dos murieron cuando su tienda de campaña…» → «…en **Texas**…» |
| 0,95 | «…a **kilómetros** del Perú…» → «…a **miles de** kilómetros…» |
| 0,92 | «El América tiene **dos** victorias…» → «…**tres** victorias…» |
| 0,91 | «…a partir del **julio**» → «…a partir del **agosto**» |
| 0,91 | «…seis puntos de sutura en el **ano**…» → «…en el **brazo**…» |

Una paráfrasis cambia muchas palabras y baja la similitud; un cambio de un dato cambia una y la deja alta. Los trigramas no separan ambos casos, y ninguna comprobación determinista lo hace, porque el cambio puede estar en cualquier palabra (cifras escritas con letras, meses, verbos, adjetivos).

**Decisión del usuario: solo coincidencia exacta.** Reutilizar mal un veredicto, publicado en la web, es peor que repetir una verificación.

**Lo que queda abierto.** Si más adelante interesa recuperar paráfrasis, la opción discutida es usar la similitud solo para proponer candidatas (por ejemplo, ≥ 0,5) y que el LLM decida si dos afirmaciones dicen exactamente lo mismo. Costaría una llamada por candidata y habría que medir antes si un modelo de 4B distingue estos cambios de una palabra; con los pares de esta medición ya se puede probar. No se hizo.

## 4. Pruebas contra la base de desarrollo (migración 009)

23 comprobaciones, todas OK:
- **Exacta:** una afirmación guardada se encuentra aunque cambien mayúsculas, tildes o puntuación; «Lima → Quito», «12 → 13 de marzo» y una paráfrasis **no** se reutilizan.
- **Similitud (apagada por defecto):** si se pide con un umbral, la base devuelve candidatas y las comprobaciones rechazan una con otra cifra.
- **Vigencia:** `insuficiente` vence a los 7 días y el resto a los 30; guardar otra vez no duplica la fila y renueva la vigencia; una afirmación vencida no se encuentra.
- **La medición es fiable:** la similitud de `pg_trgm` en la base coincide con la que usé para medir (diferencia máxima 0,0000 en 18 pares).
- **Textos reales** (extracción con Q8_0 y reutilización por coincidencia exacta). La base reutiliza exactamente lo que coincide con lo guardado, y nada más, en los 4 textos:

| Texto | Afirmaciones guardadas | El mismo texto otra vez | El texto sin su primer cuarto |
| --- | --- | --- | --- |
| 320 palabras | 5 | 5 de 5 | 0 de 5 |
| 545 palabras | 5 | 3 de 5 | 0 de 4 |
| 801 palabras | 5 | 5 de 5 | 1 de 5 |
| 1.079 palabras | 4 | 3 de 4 | 0 de 5 |

El modelo no es del todo determinista, aun con temperatura 0: el mismo texto no siempre da las mismas afirmaciones. Con coincidencia exacta, **el ahorro será modesto** (en esta muestra, 0 a 1 de 5 si el texto cambia): es el precio de no reutilizar mal. El caso de un texto repetido entero lo cubre además la copia de la verificación completa (D10).

## 5. La extracción de afirmaciones (revisión)

Con el código actual (`extraccion-v1` y las comprobaciones de [claims.py](../../backend/services/verification/claims.py)), en 40 textos reales: 172 afirmaciones aceptadas, 2 rechazadas por nombre ausente y 4 listas vacías (ver [MEDICIONES_LLM.md](MEDICIONES_LLM.md), 3.5). En esta fase se añadió el descarte de las que **dependen del texto** («esta noticia», «dicho país», «las comunidades mencionadas»): sobre esas 172 habría descartado 6 (3,5 %), todas realmente dependientes. El patrón no cuenta «ha dicho que» (de «decir»).

La lectura de las afirmaciones contra el texto la hice yo sobre 7 textos (anexo); no es una revisión de una persona del equipo.

## Anexo. Afirmaciones extraídas de cuatro textos (para revisar)

Extraídas con `extraccion-v1` y Q8_0. Los textos están en el conjunto de desarrollo de `comun_v1` y no se copian aquí.

**Artículo real de 320 palabras (huracán):**
1. Ochenta de las muertes indirectas ocurrieron en Florida, causadas por caídas durante preparativos para la tormenta, accidentes de tránsito, envenenamiento con monóxido de carbono de los generadores…
2. Catorce personas que murieron en el asilo de ancianos del condado Broward que perdió la electricidad y el aire acondicionado tras la tormenta fueron incluidas en el conteo de muertes indirectas…
3. Doce muertes en la instalación son investigadas como homicidios.
4. Siete muertes ocurrieron en el territorio continental: en Florida, dos murieron cuando su tienda de campaña quedó sumergida en una inundación…
5. Caídas de árboles causaron dos muertos en Georgia y uno en Carolina del Sur.

**Texto falso de 199 palabras (credenciales de elector):**
1. Antorcha Campesina Soteapan compró miles de credenciales de elector a favor de Cenovio Ramírez García, candidato del PRI.
2. Se encontraron miles de credenciales de elector en una casa en la que se ubicaron habitantes de las comunidades de San Fernando, Ocotal Grande y Chico…
3. Los habitantes de las comunidades mencionadas afirman que fueron engañados por Antorcha Campesina para participar en supuestos proyectos productivos. _(depende del texto: se descarta con la regla nueva)_
4. Algunos habitantes de las comunidades mencionadas declaran que compraron las credenciales para retener a los votantes… _(depende del texto: se descarta; además atribuye mal la acción, ver MEDICIONES_LLM.md 3.5)_

**Texto falso de 1.079 palabras (plataforma de inversión):**
1. Santiago Niño-Becerra anunció en el programa de TV3 'FAQs' que su plataforma Bitcoin Revolution permite a las personas ganar más de 10,000 euros al mes mediante pequeñas inversiones…
2. Hasta la fecha, más de 57.000 personas se han inscrito en la plataforma Bitcoin Revolution.
3. En el momento de escribir esta noticia, las inversiones en Bitcoin Revolution han generado más de 15.765.000 euros en ganancias. _(depende del texto: se descarta)_
4. La inversión mínima en Bitcoin Revolution es de 250 euros.
5. El sistema Bitcoin Revolution reporta un rendimiento diario superior al 2000% en el contexto de la pandemia de coronavirus.

**Artículo real de 120 palabras (ataque en Siria):**
1. El ejército estadunidense lanzó un ataque contra instalaciones en el este de Siria utilizadas por milicias respaldadas por Irán.
2. El ataque se produjo este jueves.
3. El ataque fue realizado bajo la dirección del presidente Joe Biden.
4. El ataque fue autorizado en respuesta a los recientes ataques contra el personal estadounidense y de la Coalición en Irak.
5. El ataque se llevó a cabo a principios de esta noche.
