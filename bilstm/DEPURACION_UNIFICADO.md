# Limpieza y particiones del conjunto unificado

Ejecución: `bilstm/.venv/bin/python bilstm/depurar_y_particionar.py`. La entrada es `datasets/unificado_total/noticias_binarias.csv`. Las salidas se guardan en `datasets/unificado_total/depurado/`. Los originales, el unificado completo y los modelos no se modifican. **No se entrenó ningún modelo.**

## Resultado

| Archivo | Filas | Uso |
| --- | ---: | --- |
| `noticias_depuradas.csv` | 59 099 | Todas las noticias conservadas, con nueva partición y grupo. |
| `entrenamiento.csv` | 46 795 | Ajuste de parámetros del modelo futuro. |
| `validacion.csv` | 5 849 | Selección de época e hiperparámetros. |
| `prueba_interna.csv` | 5 849 | Evaluación interna después de fijar el modelo. |
| `prueba_fuentes_reservadas.csv` | 606 | FakeDeS y FalleDesinfo apartados del entrenamiento y sus textos relacionados. |
| `excluidos.csv` | 600 | Filas retiradas y `motivo_exclusion`. |
| `reporte_limpieza.json` | — | Conteos y auditoría reproducible. |

Se partió de 59 699 noticias binarias. Se apartaron 595 filas de Acosta porque una inspección de su clase `fake` encontró sátira mezclada con desinformación. Se retira la fuente completa para evitar que su clase `real` quede como único ejemplo de ese estilo de escritura. También se retiraron dos discursos incompletos, una página con texto repetido, un fragmento de menos de cinco palabras y una sátira explícita. Las 600 filas siguen disponibles en `excluidos.csv` y en el unificado original.

No se eliminan automáticamente los titulares breves: el sistema también puede recibir titulares. Un texto corto puede ser válido; la longitud, por sí sola, no demuestra que una fila sea inútil.

## Control de fugas

Las particiones se crean con semilla 42. Antes de dividir, se unen en un mismo `grupo_particion` los registros que comparten texto completo, titular suficientemente específico, cuerpo sin titular o URL. Esto agrupa, entre otros, pares del corpus político que reutilizan la misma descripción con un titular modificado. Hay 47 135 grupos; 11 798 contienen más de una fila. Ningún grupo aparece en dos particiones.

FakeDeS y FalleDesinfo, junto con cualquier registro relacionado con ellos, se reservan por fuente. El resto se distribuye en diez pliegues estratificados por etiqueta y agrupados; ocho se usan para entrenamiento, uno para validación y uno para prueba interna. La prueba de fuentes reservadas tiene 299 falsas y 307 reales. No debe usarse para elegir hiperparámetros.

## Límites que permanecen

- El conjunto conservado sigue dominado por el corpus político: 56 761 de 59 099 filas, aproximadamente el 96 %. Por eso se deben publicar métricas por fuente y analizar los errores fuera de política.
- La limpieza automática no certifica la veracidad de cada etiqueta. Puede quedar sátira, texto incompleto o paráfrasis relacionada sin identificar. Conviene revisar manualmente una muestra por fuente antes de usarlo como base definitiva.
- La prueba de fuentes reservadas está aislada de **este nuevo entrenamiento**, pero algunos de esos datos pudieron intervenir en experimentos anteriores. No es una prueba inédita para comparar sin reservas con modelos ya existentes.
- El vocabulario, la tokenización y el límite de tokens se aplican durante el entrenamiento futuro y deben aprenderse solo de `entrenamiento.csv`.

Las columnas originales permanecen. Se añaden `particion_nueva` y `grupo_particion` a las noticias conservadas; `excluidos.csv` añade `motivo_exclusion`.
