# Evaluación de la verificación (Fase 7): arnés, piloto y lo que falta

Documento de la Fase 7 de [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md) (sección 5 y fase 7). **Estado, 15 nov 2026: el arnés de evaluación está hecho y probado, se corrió un piloto de 6 casos reales y se armó la tanda 1 de `verificacion_v1` (20 casos `contradicha`, pendientes de revisión; sección 9). El conjunto completo (80 casos) todavía no existe**: faltan 3 tandas y que una persona revise cada etiqueta. Nada se ajustó y la prueba final está intacta: ningún caso de la partición `final` se ha corrido.

## 1. Qué hay

Todo en `backend/evaluacion/` (versionado). Los casos y la evidencia guardada viven en `datasets/verificacion_v1/` (fuera de Git, como `comun_v1/`).

| Archivo | Qué hace |
| --- | --- |
| `casos.py` | Formato de un caso (`Case`), carga, **validación** de todas las reglas de 5.2 y manifiesto con SHA-256. |
| `equivalencias.py` | La tabla que traduce el veredicto de un medio de verificación a una de las cuatro conclusiones (5.2), escrita antes de etiquetar. |
| `evidencia.py` | Evidencia **en vivo** (graba) y **congelada** (reproduce), 5.3. |
| `referencias.py` | Referencia A (siempre «insuficiente») y B (el LLM sin búsqueda), 5.4. |
| `metricas.py` | F1 macro, matriz, error grave, citas y enlaces, duración, fallas, e intervalos de incertidumbre (5.5). |
| `correr.py` | El ejecutor: corre los casos con el **mismo código que la API** (`CaseVerifier`) y guarda cada resultado. |
| `informe.py`, `construir.py` | Informe `RESUMEN.md` por corrida; validar, congelar el manifiesto y la hoja de revisión. |

`CaseVerifier` guarda ahora la extracción y la traza de cada afirmación (`extraction`, `trace`), y `conclusion.py` expone la regla sobre veredictos sueltos (`conclude_verdicts`): la referencia B usa exactamente la misma regla. Pruebas: `backend/tests/test_evaluacion.py` (47; sin LLM ni internet). Backend completo: 363.

## 2. Cómo se usa

Desde la raíz, con `llama-server` levantado como en [MEDICIONES_LLM.md](MEDICIONES_LLM.md) y `backend/.env.desarrollo` con las claves (las lee el ejecutor sin imprimirlas ni tocar `backend/.env`):

```bash
# 1. Comprobar el conjunto (con --completo exige los 80 casos y su reparto; con --aprobados, la revisión humana)
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir validar --completo --aprobados
# 2. Hoja para quien revisa las etiquetas, y aplicar lo que escribió
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir hoja-revision
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir aplicar-revision hoja_revision.csv --revisor "Nombre"
# 3. Congelar el manifiesto (equivalencias.json y casos.jsonl con su SHA-256)
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.construir congelar
# 4. Primera corrida del ajuste, en vivo y con las referencias (graba la evidencia)
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.correr --particion ajuste --modo en_vivo --evidencia base --salida ajuste_1 --referencias
# 5. Las siguientes, congeladas (comparan un cambio de instrucciones en igualdad de condiciones)
PYTHONPATH=. backend/.venv/Scripts/python.exe -m backend.evaluacion.correr --particion ajuste --modo congelado --evidencia base --salida ajuste_2 --referencias
```

Cada corrida deja en `datasets/verificacion_v1/corridas/<nombre>/` los resultados caso por caso (`resultados.jsonl`, se retoma si se interrumpe), `resumen.json` y `RESUMEN.md`.

## 3. Los casos (5.2) y lo que se valida

Un caso es un texto de **al menos 100 tokens** (el mismo mínimo del análisis), la conclusión esperada, la fecha del hecho y de dónde sale la etiqueta. `validar` comprueba:

- ids y textos sin repetir; **al menos 100 tokens**; fechas válidas;
- los casos del **mismo hecho** (`grupo_evento`) van **juntos** en ajuste o en prueba final, nunca repartidos;
- `respaldada` exige **al menos 2 fuentes de dominios distintos**; las otras tres conclusiones exigen el nombre del medio de verificación, el enlace, su veredicto original y cómo se tradujo;
- el dominio del verificador y el de la página de origen del texto figuran entre los **excluidos de la evidencia** (D7): si no, el sistema podría «verificar» un texto con la propia página que lo trae o con el desmentido;
- con `--completo`: 80 casos, 20 por conclusión y **10 por conclusión en cada partición**; con `--aprobados`: todos revisados por una persona.

Campo añadido: **`tipo_texto`** (`original` o `descripcion_verificador`), por lo que se ve en el piloto (sección 7). Una descripción se escribe **sin el veredicto** y `validar` rechaza las que traen «falso», «bulo», «engañoso», «desmiente», «verificado»…; así se pueden analizar por separado.

## 4. Tabla de equivalencias (`equivalencias-v1`)

| Conclusión | Veredictos originales que se traducen |
| --- | --- |
| `contradicha` | falso, bulo, fake, mentira, desinformación, no es cierto… |
| `fuera_de_contexto` | engañoso, sin contexto, descontextualizado, fuera de contexto, no es reciente… |
| `evidencia_insuficiente` | sin pruebas, sin evidencia, inchequeable, no verificable, no se puede comprobar… |
| `respaldada` | verdadero, cierto, verdad… |
| **Se descarta** | verdad a medias, apresurado, discutible, exagerado, impreciso, parcialmente falso/cierto, «verdadero pero», sátira… |

Lo ambiguo no se traduce: el caso se descarta. Si un medio usa una palabra que no está, el caso se descarta o la tabla se amplía **por escrito y antes de correr nada**. Se guarda como `equivalencias.json` junto a los casos y entra en el manifiesto.

## 5. Evidencia en vivo y congelada (D14)

- **En vivo:** búsqueda y descarga reales; cada respuesta, cada página (con su SHA-256) y cada **falla** se guardan en `evidencia_congelada/<nombre>/`.
- **Congelado:** solo se leen esas copias. La copia es local y no se sube a Git.
- **El LLM no es idéntico de una corrida a otra**, aunque se use temperatura 0: una extracción distinta produce una consulta que no estaba grabada. Por eso una búsqueda que falta devuelve «sin resultados» (no rompe el caso) y se **cuenta**: el informe dice cuántas faltaron. Si son pocas, la comparación vale; si son muchas, hay que volver a grabar en vivo.
- En ambos modos se excluyen los medios de verificación (`FACT_CHECKERS` en `correr.py`) y los dominios propios de cada caso; **sin base de afirmaciones anteriores**: cada caso se mide por sí solo.

## 6. Métricas, referencias y umbrales

Se calculan las de 5.5: aciertos con su IC (Wilson), **F1 macro** con IC (bootstrap de casos), matriz de confusión (con una columna «sin resultado» para las fallas), el **error más grave** (decir `respaldada` cuando era `contradicha`, y el inverso), % de `evidencia_insuficiente`, duración (media y p90) y fallas por tipo. **Citas y enlaces:** cuántos veredictos con evidencia propuso el modelo y cuántos citaron bien; y de las fuentes que llegan al usuario, cuántas se **vuelven a comprobar aparte** contra la copia guardada (la página existe y la cita aparece) y cuántas direcciones **no** se habían descargado (umbral: 0). Las referencias A y B se comparan con el sistema con la **diferencia de F1 macro y su intervalo** (bootstrap sobre los mismos casos).

**Prueba final:** el ejecutor la corre solo con `--abrir-prueba-final`, con la cifra mínima de F1 macro fijada en `umbrales.json` **antes**, con el manifiesto sin cambios, y **una sola vez**: la apertura queda registrada y una segunda se rechaza.

## 7. Piloto (6 casos reales, 15 nov 2026)

Para probar el arnés se armaron 6 casos reales (2 `contradicha`, 1 `fuera_de_contexto`, 1 `evidencia_insuficiente`, 2 `respaldada`) a partir de verificaciones de Newtral, Chequeado, Maldita.es y de noticias confirmadas por varios medios. **No son parte del conjunto final ni los revisó una persona**, y no se usaron para ajustar nada. Se corrió en vivo (LLM, Tavily y descarga reales) con las referencias, y después congelado.

| Medida | Resultado |
| --- | --- |
| Aciertos | 1 de 6 (IC 95 % Wilson 0,03–0,56) |
| F1 macro | 0,083 (referencia A 0,071; referencia B 0,071). Con 6 casos no significa nada: sirve para ver que el arnés mide. |
| Citas | de 21 veredictos con evidencia, 19 con la cita bien hecha (90,5 %); **18 fuentes presentadas, las 18 comprobadas aparte contra la copia; 0 direcciones inventadas** |
| Duración | 34–59 s por caso en vivo (media 49,6 s, p90 56 s); 18 s en congelado |
| Costo | **54 búsquedas** (1 crédito de Tavily cada una, 9 por caso) y 98 páginas (75 con texto, 19 de tipo no admitido —sobre todo PDF—, 4 con error HTTP); 1,6 MB de evidencia |
| Repetición congelada | las 6 conclusiones coincidieron con la corrida en vivo; **7 búsquedas faltaron** (consultas distintas por el no determinismo del LLM) y se contaron |

### Qué se aprendió

1. **El texto de los casos es el problema de diseño más serio.** Los verificadores casi nunca reproducen un texto original de 100 tokens: describen el contenido (un vídeo, una imagen, una publicación de 35 palabras). De los 6 casos, solo 3 tienen texto original; los otros 3 son una descripción que escribí **sin el veredicto**. Un texto original corto (35 palabras, como el mensaje sobre Maricarmen) ni siquiera llega al mínimo. Hay que decidir qué se admite (sección 8).
2. **La conclusión `respaldada` casi no se alcanza.** Las dos noticias verdaderas terminaron en `evidencia_insuficiente`: con 5 afirmaciones por caso y la regla «todas `apoyada`», basta una sin evidencia o una cita mal hecha. Ya había salido en la Fase 5; ahora se puede medir y ajustar con el conjunto de ajuste.
3. **`fuera_de_contexto` por afirmación sigue siendo poco fiable:** hechos ciertos y sencillos («Luis Galarreta será primer vicepresidente a partir del 15 de julio») salieron `fuera_de_contexto`.
4. **Un caso con 5 afirmaciones cuesta ~50 s y ~9 búsquedas.** Una corrida en vivo de 40 casos son ~360 créditos de Tavily y ~35 minutos; el ajuste en vivo y la prueba final en vivo suman ~720, y el cupo gratis es de 1.000 al mes (en las fases anteriores se gastaron unos 100 a 150, por estimación, y 54 en el piloto). Las corridas congeladas no gastan créditos.
5. **El 19 % de las páginas descargadas fueron «tipo no admitido»**, casi todas PDF (informes, comunicados, leyes): el sistema las descarta. Puede ser evidencia útil perdida; no se midió cuánto.
6. **La referencia B (LLM sin búsqueda) da `contradicha` a casi todo**; ya con 6 casos se ve por qué la referencia B es un listón que conviene medir con más casos.

## 8. Lo que falta y necesito que decidas

**Respuesta recibida (15 nov 2026): «Sí, por tandas»** a «¿Armo los 80 casos por tandas de 20 con descripciones y noticias falsas, y tú los revisas?». Con eso quedan tomadas la 1 (revisa el usuario), la 2 (opción b+c, con originales cuando existan), la 3 (medios IFCN en español, últimos 12 meses) y la 5 (tandas de 20). **La 4 (presupuesto de búsqueda) sigue sin respuesta**: hasta que se conteste se itera solo con corridas congeladas y no se hace ninguna en vivo.

Lo que sigue es la lista original, en el orden en que bloqueaba (nada de esto lo decido yo):

1. **¿Quién revisa las etiquetas?** El plan pide que *una persona* revise cada etiqueta y la equivalencia aplicada, y descarte las dudosas. Yo puedo preparar los casos candidatos y la **hoja de revisión** (ya existe: `construir hoja-revision`), pero no sustituirla.
2. **¿Qué texto se admite?** Opciones: (a) solo **textos originales** de ≥ 100 tokens (más fiel al producto, pero muy pocos casos de verificadores); (b) además **descripciones** escritas sin el veredicto cuando el original no se puede recuperar (más casos, menos realistas; se analizan por separado con `tipo_texto`); (c) completar con **noticias falsas publicadas** que el verificador desmintió y que siguen en línea. Recomiendo (b)+(c), con (a) preferido siempre que exista.
3. **¿De qué medios y de qué fechas?** Propongo los que firman el código de la IFCN y publican en español (Maldita.es, Newtral, Chequeado, Colombiacheck, EFE Verifica, AFP Factual, Animal Político, La Silla Vacía…), con hechos de **los últimos 12 meses** para que la búsqueda de hoy los encuentre. Para `respaldada`, noticias de varios medios independientes.
4. **¿Presupuesto de búsqueda?** Con el cupo gratis de Tavily solo cabe una corrida en vivo de ajuste y la de la prueba final, sin margen. Opciones: una cuenta de pago (unos 0,008 USD por crédito: ~6 USD las dos corridas), recortar las consultas por afirmación, o iterar solo con corridas congeladas.
5. **Reparto de tiempo.** Armar 80 casos fiables lleva mucho más que el arnés: cada uno exige encontrar la verificación, recuperar o escribir el texto, y comprobar la equivalencia. Puedo preparar los candidatos por tandas (por ejemplo 20 por vez, una tanda por conclusión) para que los revises en cuanto estén.

## 9. Armado por tandas

Una tanda por conclusión, de 20 casos (10 `ajuste` + 10 `final`). Las etiquetas salen de verificaciones publicadas; **ninguna cuenta hasta que la persona que revisa la apruebe** (`revision: pendiente`).

### Tanda 1: `contradicha` (20 casos: vv1-001…002 del piloto y vv1-007…024 nuevos)

| Medio | Casos | País |
| --- | ---: | --- |
| Newtral | 5 | España |
| Chequeado | 4 | Argentina |
| Ecuador Chequea | 4 | Ecuador |
| La República (Verificador) | 4 | Perú |
| Maldita.es | 2 | España |
| La Silla Vacía (Detector de Mentiras) | 1 | Colombia |

Hechos entre enero y noviembre de 2026 (verificaciones del 7 ene al 14 nov), 20 grupos de evento distintos. Tipos de falsedad: vídeos o fotos reutilizados (Chávez, Messi, temporal de Brasil, Lambayeque, Chupaca), contenido hecho con IA (captura de Trump, titular de OKDiario, foto de Netanyahu, audios de De la Espriella), suplantaciones y estafas (piloto), encuestas y cifras falsas (IMOP, mapa del Senado de EE. UU., planes sociales de Milei), rumores de muerte (Zelenski, Alina Manrique), pseudociencia (NASA) y pánico económico o sísmico (feriado bancario, terremoto en Lima, USS Abraham Lincoln).

**Cómo se hizo:**

- **Texto:** los 20 son `descripcion_verificador`, escritos sin el veredicto ni las pruebas del medio (`validar` rechaza «falso», «bulo», «desmiente»…). Ningún medio publica el texto original de 100 tokens de estos hechos: son vídeos, audios e imágenes. Para llegar a 100 tokens añadí 1 o 2 frases de **contexto neutro** (qué es una provincia, qué es el PIB, qué es un portaaviones) o repetí lo que dice la publicación; ninguna aporta evidencia sobre la veracidad. Estas frases las revisa la persona que aprueba el caso.
- **Reparto:** las dos piezas del piloto (vv1-001 y vv1-002) **se quedan en `ajuste`**, porque ya se corrieron y se vieron sus resultados; los 18 nuevos se barajaron con semilla fija (`random.Random("verificacion_v1:contradicha")` sobre los ids ordenados): 8 a `ajuste` y 10 a `final`. Resultado: 10 y 10.
- **Dominios excluidos de la evidencia:** el del medio de verificación de cada caso (más `infobae.com` en vv1-020, que cubrió el mismo audio). Otros verificadores sí pueden aparecer si cubrieron el mismo hecho (riesgo de la sección 10).
- **Revisión:** `datasets/verificacion_v1/hoja_revision_tanda1.csv` (una fila por caso, con la columna `notas_del_armado` para que se vean mis dudas; `decision` = `aprobado` o `descartado`, `nota` libre; se aplica con `aplicar-revision`). La hoja trae también los 4 casos del piloto de otras conclusiones, que aún no se revisan: se dejan en blanco.

**Dudas que dejo señaladas en la hoja:**

1. **Maldita.es (vv1-014 y vv1-015):** la página que leí no muestra la etiqueta de la escala de Maldita, solo «No, … es un titular hecho con IA» y «no es real»; **asumí «Bulo»** (está en la tabla de equivalencias). Si el revisor no lo acepta, se descartan.
2. **Newtral y Chequeado:** los veredictos «Falso» salen del titular o del cuerpo de la nota (Newtral no muestra una etiqueta aparte en el texto extraído).
3. **vv1-011 (Zelenski):** el medio dice que «no hay pruebas» de la muerte y presenta evidencia de que sigue vivo; lo traduje como `contradicha` por el titular («no ha sido asesinado»), no como `evidencia_insuficiente`. Hay que confirmarlo.
4. **vv1-017 (Alina Manrique):** es una persona real; el caso nombra a una periodista que no murió. Si prefiere no incluirlo, se descarta y se reemplaza.
5. **Fecha de la verificación frente a hoy:** los de noviembre (vv1-010 a vv1-014, vv1-022) están a días de hoy; la web aún puede no tener copias.

**Pendiente de las 3 tandas siguientes:** `fuera_de_contexto` (20), `evidencia_insuficiente` (20) y `respaldada` (20; aquí sí se puede usar texto original de noticias confirmadas). En el piloto ya hay en `ajuste`: 1 `fuera_de_contexto`, 1 `evidencia_insuficiente` y 2 `respaldada`; se completan a 10 y 10.

## 10. Riesgos de validez a tener presentes

- **Se ajusta solo con el conjunto de ajuste**; la prueba final no se mira. El piloto no cuenta como ajuste (no cambió nada).
- **Fugas por el tiempo:** una verificación publicada hace meses puede no coincidir con lo que muestra hoy la web; cada caso lleva su fecha y los dudosos se descartan.
- **Los textos descriptivos** los escribe quien arma el conjunto (yo, en el piloto): pueden arrastrar mi redacción. La revisión humana y analizarlos aparte lo mitigan.
- **Con 40 casos por conjunto** los intervalos son anchos (un solo caso mueve el F1 macro varios puntos): las cifras son orientativas y el informe lo dirá.
