# Fase A — recopilación y auditoría inicial de datasets

**Fecha:** 7 de octubre de 2026. **Estado:** terminada para los cuatro corpus principales descargados; la aceptación definitiva de registros individuales corresponde a la fase B. No se han creado particiones nuevas ni entrenado modelos.

Los originales están en `D:\ScanTrue\datasets\raw`. Se conservaron comprimidos o en su formato original. El inventario reproducible con tamaño, SHA-256, columnas, recuentos, vacíos y cruces de texto exacto está en [phase_a_inventory_20261007_v2.json](../datasets/audit/phase_a_inventory_20261007_v2.json). El lector utilizado está en [audit_phase_a.py](audit_phase_a.py). Para leer Excel se utilizó el Python auxiliar de Codex con `openpyxl`; **no se instaló nada en `.venv`**.

## 1. Descargas y procedencia

| Corpus | Archivo(s) guardado(s) | Procedencia y versión | Licencia declarada |
| --- | --- | --- | --- |
| Spanish Fake News Corpus v1/v2 | [ZIP del repositorio](../datasets/raw/FakeNewsCorpusSpanish/FakeNewsCorpusSpanish_732f4870abd8d3f5ab4956fd92b040a7913614e3.zip) | [Autores, GitHub](https://github.com/jpposadas/FakeNewsCorpusSpanish), commit `732f4870abd8d3f5ab4956fd92b040a7913614e3` | CC BY 4.0 en el repositorio. |
| ISOT Fake News | [ZIP original](../datasets/raw/ISOT/News-_dataset_2023-03-09.zip) | [Laboratorio ISOT, Universidad de Victoria](https://onlineacademiccommunity.uvic.ca/isot/2022/11/27/fake-news-detection-datasets/); archivo publicado el 9 de marzo de 2023 | No se identificó una licencia explícita en la página de descarga o la descripción. Revisar condiciones antes de distribuir datos o modelos derivados. |
| PolyglotFakeFacts v2.0 | [Archivos originales](../datasets/raw/PolyglotFakeFacts_v2) y [metadatos de origen](../datasets/raw/PolyglotFakeFacts_v2/source_metadata.json) | [Mendeley Data, DOI 10.17632/8yfrm6z9dx.1](https://data.mendeley.com/datasets/8yfrm6z9dx/1), versión 1 publicada el 17 de febrero de 2026 | CC BY 4.0. Los cuatro SHA-256 coinciden con los publicados por Mendeley. |
| Pérez-Rosas et al. 2018 | [ZIP original](../datasets/raw/PerezRosas2018/fakeNewsDatasets_2018-08-20.zip) | [Página de descargas de Rada Mihalcea](https://web.eecs.umich.edu/~mihalcea/downloads.html), 20 de agosto de 2018; [artículo COLING 2018](https://aclanthology.org/C18-1287/) | La página de la autora declara GNU GPL para sus datasets y software. Confirmar las obligaciones aplicables antes de redistribuir. |

Todas las descargas se completaron. **No necesitas descargar archivos manualmente en esta fase.** No se descargó [USMSC](https://huggingface.co/datasets/gabrielhuav/Unified-and-Balanced-Spanish-Fake-News-Corpus): sigue siendo una fuente condicional porque integra el corpus español original, contiene sátira con fuerte sesgo de fuente y su CSV publicado presenta un error de lectura en el visor. Tampoco se descargaron LIAR ni FakeNewsNet, excluidos del primer objetivo de artículos completos.

## 2. Estructura y recuentos observados

| Conjunto físico | Registros | Etiquetas observadas | Vacíos de titular / cuerpo | Observación |
| --- | ---: | --- | ---: | --- |
| Español v1 `train.xlsx` | 676 | 338 `Fake`, 338 `True` | 0 / 0 | 7 columnas: ID, clase, tema, fuente, titular, texto y enlace. |
| Español v1 `development.xlsx` | 295 | 142 `Fake`, 153 `True` | 0 / 0 | 1 texto exacto repetido dentro del archivo. |
| Español v2 `test.xlsx` | 572 | 286 `False`, 286 `True` | 72 / 0 | Etiqueta falsa escrita `False` en vez de `Fake`; 90 casos sociales falsos según los autores, sin columna explícita de tipo. |
| ISOT `True.csv` | 21 417 | REAL, implícita por archivo | 0 / 1 | Titular, cuerpo, tema y fecha. |
| ISOT `Fake.csv` | 23 481 | FALSA, implícita por archivo | 0 / 630 | Muchos cuerpos repetidos o vacíos; comprobar antes de usar. |
| Pérez-Rosas `fakeNewsDataset` | 480 textos | 240 `fake`, 240 `legit` | No aplica | Un archivo `.txt` por noticia; algunas falsas se escribieron para el estudio. |
| Pérez-Rosas `celebrityDataset` | 500 textos | 250 `fake`, 250 `legit` | No aplica | Dominio celebridades, separado del anterior. |
| Polyglot `Fake.xlsx` | 4 912 | `fake` | 15 / 25 | Contiene 289 originales en español y 445 en inglés. |
| Polyglot `Real.xlsx` | 5 294 | `real` | 16 / 36 | Contiene 480 originales en español y 137 en inglés. Incluye una columna final sin nombre. |
| Polyglot `20.xlsx` | 2 041 | 982 `fake`, 1 059 `real` | 6 / 15 | Representación de una parte del corpus; no es un dataset adicional. |
| Polyglot `80.xlsx` | 8 165 | 3 930 `fake`, 4 235 `real` | 25 / 46 | Representación del resto, pero cruza 54 textos exactos con `20.xlsx`. |

En Polyglot, `Fake.xlsx` + `Real.xlsx` suman **10 206 registros**. `20.xlsx` + `80.xlsx` también suman **10 206**, por lo que son organizaciones alternativas del mismo material. **No se deben concatenar los cuatro archivos.** Si se toma `Fake.xlsx` + `Real.xlsx` como fuente de lectura, solo **1 351** registros declaran idioma original español o inglés: 769 español (289 falsos, 480 reales) y 582 inglés (445 falsos, 137 reales). Las mayúsculas del campo idioma son inconsistentes en `20.xlsx`/`80.xlsx` y deberán normalizarse. Las traducciones inglesas de textos originalmente escritos en otros idiomas quedan fuera del alcance.

Los autores de Spanish Fake News Corpus describen v1 como noticias de enero a julio de 2018, y v2 como material de noviembre de 2020 a marzo de 2021. [Descripción original](https://github.com/jpposadas/FakeNewsCorpusSpanish). La descripción de ISOT indica que sus noticias reales provienen de Reuters y las falsas de fuentes marcadas como no fiables; esto crea una asociación fuerte entre **fuente y etiqueta**. [Descripción ISOT](https://onlineacademiccommunity.uvic.ca/isot/wp-content/uploads/sites/7295/2023/02/ISOT_Fake_News_Dataset_ReadMe.pdf).

## 3. Incidencias de duplicación y calidad

- **Español v1:** 4 huellas de texto idénticas aparecen tanto en `train.xlsx` como en `development.xlsx`. No se moverá ni utilizará esa validación sin resolverlas; se conservará registro de IDs y de la decisión en fase B. No se encontraron coincidencias exactas de cuerpo entre v1 y el `test.xlsx` de v2, aunque faltan las comprobaciones de similitud y evento.
- **ISOT:** `Fake.csv` contiene 23 481 filas pero solo 17 448 huellas únicas de cuerpo o titular; `True.csv`, 21 417 filas y 21 189 huellas únicas. Esto es una señal de duplicación considerable, especialmente en la clase falsa. No hubo coincidencias exactas entre los conjuntos falso y real bajo esta comparación.
- **Polyglot:** `20.xlsx` y `80.xlsx` comparten 54 textos exactos. En `Fake.xlsx` hay 4 867 huellas únicas entre 4 912 registros; en `Real.xlsx`, 4 228 entre 5 294. Muchos casos de `20.xlsx`/`80.xlsx` coinciden con `Fake.xlsx`/`Real.xlsx`. No se detectaron textos exactos idénticos entre `Fake.xlsx` y `Real.xlsx`, ni entre `train.xlsx` o `test.xlsx` del corpus español y esos dos archivos de Polyglot. Todavía hay que buscar noticias semejantes y versiones del mismo evento.
- **Alcance de la comprobación:** «huella exacta» significa SHA-256 del cuerpo, o titular si el cuerpo está vacío, tras convertir a minúsculas y unificar espacios. No identifica paráfrasis, traducciones ni artículos del mismo hecho. El recuento de vacíos se basa en celdas presentes; la correspondencia semántica entre texto y etiqueta requiere revisión muestral humana.

## 4. Decisión al cierre de fase A

| Corpus | Decisión provisional |
| --- | --- |
| Spanish v1 | **Aceptar para preparación** de entrenamiento/validación, después de resolver las 4 coincidencias entre splits y auditar etiquetas. |
| Spanish v2 | **Reservar** como prueba española de otro período; identificar y separar los 90 casos sociales antes de evaluar artículos. |
| Polyglot v2 | **Aceptar para preparación condicional** de solo originales español/inglés. Leer `Fake.xlsx` + `Real.xlsx` una vez; deduplicar, revisar fuente/etiqueta y mantener una prueba española de otro origen si los datos lo permiten. |
| ISOT | **Condicional** para entrenamiento inglés: revisar duplicados, sesgo de fuente y condiciones de uso. Ninguna puntuación interna de ISOT se usará como prueba principal. |
| Pérez-Rosas | **Reservar** como evaluación inglesa secundaria o experimento pequeño; mantener separados sus dos dominios y documentar el origen sintético de parte de los falsos. |
| USMSC | **No incorporar** por ahora; resolver integridad, solapamiento y sesgo de sátira solo si los corpus aceptados resultan insuficientes. |

**Siguiente fase:** estandarizar etiquetas y campos, revisar muestras, validar idioma original, resolver duplicados exactos y aproximados, definir grupos de evento y congelar particiones. No se han modificado los archivos originales.
