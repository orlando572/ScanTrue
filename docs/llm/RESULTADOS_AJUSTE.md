# Fase 7: primera corrida sobre el conjunto de ajuste (`ajuste_1`)

**Fecha:** 16 nov 2026. **Plan:** [PLAN_INCREMENTO_2.md](PLAN_INCREMENTO_2.md), Fase 7. **Conjunto:** `verificacion_v1`, partición de ajuste (ver [EVALUACION_VERIFICACION.md](EVALUACION_VERIFICACION.md), sección 9). Los datos de la corrida están en `datasets/verificacion_v1/corridas/ajuste_1/` (fuera de Git; `RESUMEN.md`, `resumen.json` y `resultados.jsonl`).

**Esto NO es la prueba final.** Es la línea de partida sobre los casos que sirven para ajustar el sistema. La prueba final (los otros casos del conjunto) no se ha abierto ni se puede abrir: el conjunto no se puede congelar mientras la clase `evidencia_insuficiente` tenga 6 casos de 20.

## 1. Qué se corrió

- **Sistema:** el de `feature/llm` tal como está (`extraccion-v2`, 3 afirmaciones por noticia, 1 consulta por afirmación, 4 páginas por afirmación, Tavily, LLM `Qwen3-4B-Instruct-2507-Q8_0` en `llama-server`, RTX 5060). Sin fuente previa de Google ni base de afirmaciones: el ejecutor de evaluación mide cada caso por sí solo y excluye los medios de verificación y los dominios del caso.
- **Modo:** en vivo (búsquedas y descargas reales); toda la evidencia quedó guardada en `evidencia_congelada/ajuste1/`, así que **las siguientes corridas pueden ser congeladas, sin gastar créditos de Tavily**.
- **Casos:** 33 aprobados de la partición de ajuste (10 `contradicha`, 10 `fuera_de_contexto`, 10 `respaldada`, 3 `evidencia_insuficiente`).
- **Referencias:** A (siempre «evidencia insuficiente») y B (el mismo LLM sin búsqueda).
- **Duración:** 23,5 s de media por caso (p90 33,5 s). Sin fallas de ejecución.

## 2. Resultado

| Medida | Valor |
| --- | --- |
| Aciertos | **5 de 33** (15,2 %; IC 95 % [0,067; 0,309]) |
| **F1 macro** | **0,144** (IC 95 % [0,036; 0,248]) |
| Referencia A (siempre insuficiente) | 0,042 [0,000; 0,087]; el sistema la supera por 0,102 (IC de la diferencia [-0,008; 0,207], incluye 0) |
| Referencia B (LLM sin búsqueda) | 0,183 [0,047; 0,294]; **el sistema no la supera** (diferencia -0,038, IC [-0,169; 0,101]) |
| Error más grave («respaldada» cuando era contradicha) | 0 |
| Error grave inverso («contradicha» cuando era respaldada) | 2 |
| Casos que terminan en «evidencia insuficiente» | **57,6 %** (19 de 33) |
| Veredictos con evidencia: citas bien hechas | 58 de 61 (**95,1 %**) |
| Fuentes que llegan al usuario comprobadas aparte | 56 de 56 (100 %) |
| **Direcciones inventadas / no descargadas** | **0** |

| Clase | Casos | Precisión | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| `respaldada` | 10 | 0,000 | 0,000 | 0,000 |
| `contradicha` | 10 | 0,333 | 0,200 | 0,250 |
| `fuera_de_contexto` | 10 | 0,286 | 0,200 | 0,235 |
| `evidencia_insuficiente` | 3 | 0,053 | 0,333 | 0,091 |

Matriz de confusión (filas: esperado; columnas: obtenido):

| esperado \ obtenido | respaldada | contradicha | fuera de ctx. | insuficiente |
| --- | ---: | ---: | ---: | ---: |
| respaldada | 0 | 2 | 2 | 6 |
| contradicha | 0 | 2 | 1 | 7 |
| fuera de ctx. | 1 | 2 | 2 | 5 |
| insuficiente | 0 | 0 | 2 | 1 |

## 3. Qué dice frente al criterio de aceptación

Criterios del plan: 0 URL inventadas, citas válidas ≥ 95 % y F1 macro por encima de las dos referencias y de la cifra mínima.

| Criterio | Resultado | ¿Cumple? |
| --- | --- | :---: |
| 0 direcciones inventadas | 0 | Sí |
| Citas válidas ≥ 95 % | 95,1 % (58 de 61), justo en el umbral | Sí, por poco |
| F1 macro por encima de A y de B | Supera a A (sin significancia) y **no supera a B** | **No** |
| F1 macro por encima de la cifra mínima | Aún no se ha fijado | — |

**Lectura honesta:** el sistema es **seguro** (no inventa fuentes y sus citas existen) pero **todavía no es exacto**: con estos casos, su conclusión no es mejor que preguntarle al mismo LLM sin buscar nada. Esto es lo que el plan esperaba encontrar antes del ajuste (la regla de conclusión «se equivoca con facilidad»); los números lo confirman y lo cuantifican.

## 4. Diagnóstico (de `resultados.jsonl`)

1. **Se rinde demasiado a «evidencia insuficiente»** (19 de 33). Es el error dominante: 7 de 10 `contradicha`, 6 de 10 `respaldada` y 5 de 10 `fuera_de_contexto` terminan ahí. Es la salida «segura» (no le dice mal al lector que algo es cierto o falso), pero no aporta.
2. **Tres casos no extrajeron ninguna afirmación** (vv1-011, vv1-015, vv1-021; tardaron 0,3 s): el LLM no encontró «afirmaciones concretas que se puedan comprobar» en descripciones de rumores o de una foto. Con `extraccion-v2` («las 3 más importantes… con datos concretos») el filtro es más estricto.
3. **Muchas afirmaciones sin evidencia:** de las afirmaciones que quedan en `insuficiente`, 16 de 34 son `sin_evidencia` (la búsqueda no devolvió páginas útiles, en parte porque se excluyen los verificadores y los dominios del caso), 3 `cita_no_literal` y 3 `apoyo_incompleto`.
4. **La regla de conclusión hace casi imposible `respaldada`:** exige que **todas** las afirmaciones sean `apoyada`; en los 10 casos `respaldada` solo 6 de 30 afirmaciones salieron `apoyada`, y 10 salieron `fuera_de_contexto` aunque eran hechos ciertos y bien documentados (el juez de 4B es poco fiable con `fuera_de_contexto`, como ya se midió en la Fase 4).
5. **El juez a veces contradice hechos ciertos** (2 casos `respaldada` terminaron `contradicha`; 3 de 30 afirmaciones de ese grupo salieron `contradicha`).
6. **`evidencia_insuficiente` casi no se acierta** (1 de 3), pero con 3 casos no se puede concluir nada de esa clase.

## 5. Límites de estas cifras

- **33 casos** (ajuste): los intervalos son anchos y un solo caso mueve el F1 macro varios puntos. Son cifras orientativas.
- **La clase `evidencia_insuficiente` tiene 3 casos** en ajuste.
- **Una sola corrida:** el LLM no es idéntico de una corrida a otra, aun con temperatura 0.
- **Descripciones, no textos originales:** los casos son `descripcion_verificador` (redactados por quien arma el conjunto), que se parecen menos al texto real que llegaría al sistema.
- **Sin fuente previa de Google:** la evaluación la excluye (los medios de verificación se descartan para no copiar la respuesta), así que mide el sistema sin esa ayuda.
- **Las citas válidas están justo en el umbral** (95,1 %): con otra corrida podrían quedar por debajo.

## 6. Qué sigue (propuestas, **sin aplicar**)

El ajuste debe hacerse **solo con estos casos** y dejando anotado cada cambio. Las corridas siguientes pueden ser **congeladas** (sin gastar Tavily). Candidatos, que ya estaban anotados en [CONCLUSION_Y_TRABAJADOR.md](CONCLUSION_Y_TRABAJADOR.md) más lo que mostró esta corrida:

1. **Relajar `respaldada`:** en lugar de «todas `apoyada`», aceptar «la mayoría `apoyada` y ninguna `contradicha`».
2. **Que `fuera_de_contexto` por afirmación no decida el caso** hasta que el juez sea más fiable (candidato 5 del documento de la Fase 5).
3. **Exigir 2 fuentes de dominios distintos para dar `contradicha`** (candidato 1), para reducir las contradicciones falsas.
4. **Extracción:** revisar por qué 3 descripciones de rumores quedan sin afirmaciones (puede ser correcto en parte).
5. **Fijar la cifra mínima de F1 macro** solo después del ajuste y antes de abrir la prueba final.

Cualquier cambio de la regla de conclusión es una decisión de diseño que conviene confirmar con Orlando.
