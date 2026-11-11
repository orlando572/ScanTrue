# Texto único para el análisis

**Estado:** implementado en el backend. La migración
`db/migrations/005_texto_unico.sql` quedó aplicada al proyecto conectado como
`texto_unico` (versión `20261012004432`).

## Contrato actual

La extensión envía un único fragmento en `texto` y una `url` opcional. Si el
usuario selecciona el titular, ya forma parte de `texto`. El backend limpia esa
cadena, valida los mínimos, la recorta cuando corresponde y entrega el mismo
fragmento preparado a BiLSTM y mBERT. Nunca añade un titular separado ni
deduce que la primera línea sea un titular. Un campo `titulo` en la solicitud
recibe HTTP 422.

El fragmento preparado se guarda en `analisis.texto` y su SHA-256 en
`analisis.hash_texto`. La respuesta de historial no contiene `titulo`; el
listado ofrece `vista_previa` y el detalle ofrece `texto`. La extensión actual
ya usa esos campos y no necesitó cambios de código.

## Base de datos y conservación

Antes de aplicar 005 se contaron 16 análisis y ninguno tenía `titulo` no nulo.
La migración vuelve a comprobarlo y se detiene si encuentra uno, para no
descartar un valor histórico. Crea la RPC `crear_analisis_texto_unico` con
inserción atómica y ejecución limitada a `service_role`, retira las dos RPC
con `p_titulo` y elimina `public.analisis.titulo`. Las migraciones 001–004
permanecen intactas como historial.

Se auditó el resto de columnas: `intentos_blockchain` y
`ultimo_error_blockchain` son escritos por la cola y se conservan para
diagnóstico; `proximo_intento_blockchain` programa reintentos. Las demás
columnas sirven a la identidad, historial, modelos o verificación. El `id` de
`resultados_modelo` sigue siendo su clave primaria.

## Verificación y comunicación

Las pruebas locales comprueban el titular ya incorporado, el cuerpo sin
titular, el rechazo de `titulo` separado, la igualdad del texto enviado a los
modelos y el hash del fragmento guardado. OpenAPI anuncia solo `texto` y `url`.
La prueba HTTP con Uvicorn confirmó creación, lectura y verificación local de
blockchain; el análisis temporal se eliminó. `verificar_flujo.py` conserva la
comprobación integral para futuros despliegues. En esta sesión, su ejecución
en proceso mediante `TestClient` agotó la espera de confirmación de blockchain;
la prueba equivalente por HTTP real sí confirmó el registro.

`../FRONTEND_CONTEXT.md` describe el contrato anterior del historial y no se
editó por la restricción de trabajar solo dentro de `backend`. La persona de
frontend debe recibir la actualización de [CAMBIO_CONTRATO_MBERT.md](CAMBIO_CONTRATO_MBERT.md)
y la retirada de `titulo` de las respuestas de historial.
