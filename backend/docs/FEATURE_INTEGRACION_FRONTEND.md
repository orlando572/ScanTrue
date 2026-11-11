# Feature implementada: contrato de integración con el frontend

> Este documento registra la entrega anterior. La integración posterior de
> mBERT cambió los límites de lectura y el texto guardado; el contrato vigente
> y la nota para frontend están en [CAMBIO_CONTRATO_MBERT.md](CAMBIO_CONTRATO_MBERT.md).

**Estado: contrato y transferencia a cuenta comprobados; envío de confirmación por correo pendiente de prueba.** El contrato que recibirá la extensión está en [`../FRONTEND_CONTEXT.md`](../../frontend/docs/FRONTEND_CONTEXT.md). Los recorridos reales con Supabase y Anvil confirmaron el flujo de invitados y la incorporación a una cuenta temporal confirmada por Auth Admin.

## Objetivo y orden

La entrega permite que la extensión muestre el texto analizado, tres espacios de porcentaje y el cierre de la sesión actual. Reúne tres cambios del backend en una versión de contrato: (1) historial con texto y vista previa, (2) resultado unificado con pesos persistidos, (3) cierre de sesión. Se verificó operativamente con invitados, una cuenta temporal y blockchain. La inferencia real de mBERT sigue siendo una feature posterior, condicionada a recibir sus artefactos.

## 1. Texto e historial

- Crear una migración posterior a `003_blockchain_registry.sql` que añada `public.analisis.texto` nullable. Las filas existentes conservan `NULL`; los análisis nuevos guardan la selección completa tras una predicción válida. El hash SHA-256 sigue calculándose sobre el texto recibido sin espacios exteriores. Nunca enviar el texto, la URL ni la identidad a blockchain.
- Ampliar la creación atómica del análisis y sus resultados para guardar el texto desde el backend. Mantener la creación restringida al servidor y la lectura y eliminación bajo las políticas de propietario existentes.
- `GET /analisis?limit=20&offset=0` añadirá `vista_previa: string | null`, derivada del texto guardado y limitada a 160 caracteres de una sola línea. `GET /analisis/{id}` añadirá `texto: string | null` con la selección íntegra. No incluir `texto` completo en el listado. Las filas anteriores mostrarán ambos valores como `null`.

## 2. Tres porcentajes y resultado unificado

- Conservar `resultados.bilstm.probabilidad_falsa` y `resultados.mbert.probabilidad_falsa` en escala 0–1. Solo un modelo con `estado: "ok"` aporta un valor; `mbert` seguirá en `no_disponible` hasta existir un predictor real. El frontend multiplicará por 100. El significado es salida para la clase falsa, **no certeza factual**; no crear niveles o bandas de porcentaje.
- Añadir a `POST /analisis`, al listado y al detalle `resultado_unificado` con `probabilidad_falsa`, `modelos_utilizados`, `pesos_aplicados` y `version_regla: "media_ponderada_v1"`. El backend calculará una media de las probabilidades disponibles. Con ambos modelos los pesos iniciales son BiLSTM 0,30 y mBERT 0,70. Si solo uno responde, su peso aplicado es 1,0 y el otro 0,0. El valor se obtiene únicamente de predicciones reales; nunca se simula mBERT.
- Configurar el peso de mBERT en el backend con `ANALYSIS_MBERT_WEIGHT`, valor predeterminado `0.70` y rango válido 0–1; el peso de BiLSTM es `1 - ANALYSIS_MBERT_WEIGHT`. Exponer **pesos aplicados**, no solo configurados, para que el frontend explique un resultado con un solo modelo. Cambiar la configuración afecta únicamente análisis futuros.
- Persistir el valor unificado, los modelos participantes, los pesos aplicados y la versión de la regla junto con cada análisis, en la misma operación atómica que sus resultados. Completar los registros anteriores a partir de sus predicciones guardadas con la regla inicial; si alguno carece de datos suficientes, representar su `resultado_unificado` como `null` en historial. Conservar el valor histórico al cambiar los pesos de configuración.
- Mantener `comparacion` independiente: `coinciden` o `discrepan` solo con dos predicciones válidas. El unificado puede existir con un solo modelo y debe mostrarlo explícitamente. No añadir una clase global ni presentar el porcentaje como prueba de veracidad.

## 3. Cierre de la sesión actual

- Añadir `POST /sesiones/cerrar` con `Authorization: Bearer <access_token>`, sin cuerpo y con respuesta `{ "cerrada": true }`. Verificar la identidad y pedir a Supabase Auth la revocación de la sesión **local/actual**, sin cerrar las demás sesiones del usuario.
- Si Auth rechaza el token, responder como sesión inválida; si el proveedor no responde, indicar indisponibilidad para que el cliente pueda decidir si reintenta. El frontend retirará sus tokens locales tras una respuesta satisfactoria. Un JWT de acceso emitido puede seguir válido hasta su vencimiento.

## Entrega y sincronización

1. La migración `004_frontend_contract.sql` se aplicó al proyecto Supabase conectado el 10 de octubre de 2026 (versión `20261010224814`). Se verificaron las columnas nuevas, la función reservada a `service_role`, las políticas RLS y la ausencia de advertencias de seguridad. PostgREST expone la RPC y rechaza con HTTP 400 una solicitud inválida sin crear registros. La tabla tenía cero filas; la reconstrucción de registros antiguos no pudo comprobarse con datos reales.
2. Actualizar OpenAPI, la documentación de operación y el estado interno al terminar. El documento [`../FRONTEND_CONTEXT.md`](../../frontend/docs/FRONTEND_CONTEXT.md) ya fue entregado y no se modifica; mantener el contrato del backend compatible con sus nombres de campos y su ejemplo de un solo modelo.
3. El 10 de octubre de 2026, `backend/verificar_flujo.py` pasó con dos invitados reales: análisis BiLSTM, resultado unificado, texto y vista previa persistidos, RLS de acceso ajeno, renovación, cierre de sesión, blockchain, respuestas de degradación y eliminación del análisis de prueba. Una segunda comprobación inició sesión en una cuenta temporal confirmada por Auth Admin, transfirió un análisis y verificó que el invitado perdió acceso. Los datos temporales se eliminaron. El registro por correo con un buzón real quedó sin completar porque Auth respondió `429 over_email_send_rate_limit`; el backend ahora devuelve 429 en ese caso. El cálculo local con uno y dos modelos y fallo de un modelo se revisó previamente; mBERT real sigue pendiente. También quedan sin comprobar casos históricos anteriores a 004, que no existían en este proyecto.

## Feature posterior: mBERT

Cuando exista checkpoint, tokenizador, mapa de clases y evaluación, incorporar el predictor al adaptador actual y normalizar su salida como `probabilidad_falsa` de la clase falsa. La misma respuesta y el cálculo ponderado funcionarán sin cambiar el contrato del frontend. Revisar entonces calidad y calibración del porcentaje unificado con datos de evaluación; cualquier nueva regla tendrá una versión distinta para preservar la interpretación de los registros históricos.
