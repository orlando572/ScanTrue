# Paso 7: protocolo para una prueba española inédita

**Fecha:** 8 de octubre de 2026. **Estado:** preparado antes de ver cualquier predicción en un conjunto nuevo. Todavía no existe en el proyecto un conjunto que cumpla los criterios. Los resultados de los pasos 5–6 permanecen congelados.

## Unidad y etiqueta

Una fila representa **una noticia en español** con titular y cuerpo, publicada o difundida como noticia. `0=REAL` exige evidencia específica que respalde el hecho central; `1=FALSA` exige una refutación específica de ese hecho. La fuente por sí sola no determina la etiqueta. Se excluyen sátira declarada, opinión, verificaciones que describen un bulo en vez de reproducir la noticia, afirmaciones aisladas, publicaciones sociales sin cuerpo de artículo, contenido sintético sin hecho verificable y casos ambiguos. Cada fila debe tener URL de la noticia, URL de evidencia, fuente, fecha, tema, grupo de evento, base de derechos de uso y revisión documentada.

La [plantilla CSV](plantilla_noticias.csv) fija las columnas `id,title,body,label,source,url,published_date,topic,event_id,evidence_url,rights_basis,reviewed_by,review_status`. El campo `review_status` debe ser `approved` después de comprobar manualmente el texto y la evidencia. El cuerpo completo se mantiene local; los reportes de evaluación mostrarán IDs, metadatos y métricas, sin republicar artículos.

## Criterios fijados antes de puntuar

- Meta mínima: **100 REAL y 100 FALSA**, al menos **tres medios o fuentes por clase**, cuatro temas y presencia de textos cortos (<200 palabras), medios (200–499) y largos (≥500). Estos mínimos permiten una evaluación inicial, no aseguran representatividad.
- Mezclar medios y temas **dentro de ambas clases**; evitar que un dominio equivalga casi siempre a una etiqueta. Mantener juntos todos los textos del mismo `event_id` y evitar eventos que aparezcan en cualquier dato anterior.
- Registrar SHA-256 del CSV y de las decisiones de inclusión **antes de inferir**. Auditar duplicados internos, URL, título y texto frente a todos los datos del mBERT inicial y todos los CSV BiLSTM, incluidos los conjuntos ya evaluados. Revisar manualmente paráfrasis y eventos compartidos; un control léxico negativo no acredita independencia.
- Verificar licencia o permiso de uso del texto y atribución de la fuente. No publicar cuerpos de noticias de terceros en los reportes.
- Fijar los mismos dos checkpoints del [paso 6](../evaluations/bilstm_step6_20261008_v1/protocol.json): E1 anterior, 256 tokens, entrada `titulo/cuerpo`; nuevo semilla 43, 512 tokens, entrada `title + espacio + body` como una secuencia. Etiquetas `0=REAL,1=FALSA`, umbral **0,5**. No entrenar, calibrar ni elegir longitud, semilla o umbral con esta prueba.
- Puntuar ambos modelos **una sola vez** sobre los mismos IDs. Publicar matriz, soporte, precisión, recall y F1 por clase; F1 macro, exactitud, exactitud balanceada, falsas alarmas, AP y Brier; predicciones por ID y diferencias pareadas con incertidumbre agrupada por fuente/evento. Informar por fuente, tema y longitud, incluidos los casos de error.

## Auditoría previa automatizada

El script [step7_audit_fresh_dataset.py](../step7_audit_fresh_dataset.py) valida esquema, etiquetas, campos, mínimos, duplicados y coincidencias exactas con los datos históricos **sin cargar modelos ni puntuar**. Uso desde `D:\ScanTrue`:

```powershell
& 'C:\Users\Evechan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\mBERT\step7_audit_fresh_dataset.py 'D:\ruta\noticias_nuevas.csv'
```

Su salida se crea en una carpeta nueva bajo `mBERT/final_test_step7/audits/`. El script siempre deja `manual_event_review_completed=false`: la revisión de eventos y etiquetas necesita evidencia y decisión humana antes de autorizar la evaluación final. Si no se alcanza la meta mínima o hay coincidencias, los datos solo podrán usarse como diagnóstico separado, no para afirmar superioridad en la prueba final.

## Disponibilidad examinada

La [auditoría local previa](../../datasets/audits/mis_datasets_20261007_v1/AUDITORIA.md) identificó copias de Posadas ya usadas, USMSC/Edds con procedencia insuficiente y solapamiento, y FactOReS como otra tarea. La búsqueda de alternativas públicas tampoco proporcionó aquí una prueba lista: [FakesStorage](https://github.com/alcorpas10/FakesStorage) publica noticias falsas con recuentos de palabras pero no el par REAL/FALSA de cuerpos completos; [NewsPolyML](https://github.com/news-polygraph/NewsPolyML) etiqueta principalmente *afirmaciones* de verificaciones y normaliza categorías con un modelo, por lo que su artículo de verificación no es la noticia cuya veracidad se etiqueta; el [Spanish Fake News Dataset de 2025](https://zenodo.org/records/15592390) reúne principalmente mensajes falsos de formatos mixtos, sin contraparte REAL adecuada para esta prueba de artículos.

Hasta recibir un conjunto nuevo y aprobar su auditoría, **no se calculará una nueva métrica final**. El [cierre retrospectivo](CIERRE_RETROSPECTIVO.md) declara lo que sí se observó y sus límites.
