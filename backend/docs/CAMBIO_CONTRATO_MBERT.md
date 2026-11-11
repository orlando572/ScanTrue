# Actualización de contrato para la persona de frontend

La guía `FRONTEND_CONTEXT.md` ya se entregó y no se modifica. Este documento
registra el cambio que debe comunicarse junto a ella antes de actualizar la
extensión.

- `POST /analisis` recibe `texto` y, opcionalmente, `url`. El titular forma parte
  de `texto` si se seleccionó; un campo `titulo` separado devuelve 422.
  El backend exige **al menos 100 tokens por cada modelo disponible**, contados
  con el tokenizador propio de BiLSTM y de mBERT. El frontend solo puede mostrar
  una estimación; el `422` del backend decide si falta contexto.
- El máximo de 192 tokens ya no es un límite de solicitud: **BiLSTM lee como
  máximo sus primeros 192 tokens**. mBERT lee como máximo 512 de sus tokens,
  incluidos los especiales. Si el texto supera ese límite, el backend analiza
  el prefijo y devuelve `texto_recortado: true` en la respuesta de creación.
- `GET /analisis` muestra la vista previa y `GET /analisis/{id}` devuelve en
  `texto` **solo el fragmento analizado**, no el texto original que pudo haber
  enviado la extensión. `hash_texto` identifica ese mismo fragmento. Ninguna
  de las dos respuestas incluye ya `titulo`; el listado usa `vista_previa`.
- Con mBERT operativo, `resultados.mbert.estado` es `ok` y su
  `probabilidad_falsa` llega en escala 0–1. `resultado_unificado` ya trae el
  valor y los pesos aplicados; el frontend no debe recalcularlo. Si el modelo
  falla o falta, mostrar “No disponible” según `estado`.
- `GET /metricas` mantiene la evaluación BiLSTM por defecto; usar
  `GET /metricas?modelo=mbert` para las evaluaciones del checkpoint mBERT.
  Ambas respuestas tienen la misma estructura. Los porcentajes son salidas
  experimentales de clasificadores y no verificaciones de hechos.

La API no añade campos al listado ni al detalle para indicar si un análisis
histórico fue recortado: `texto_recortado` está en la respuesta inmediata de
creación. Los registros anteriores conservan el texto con el que se guardaron.
