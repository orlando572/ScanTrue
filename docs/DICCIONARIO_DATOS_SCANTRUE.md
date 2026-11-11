# DICCIONARIO DE DATOS DE SCANTRUE

Este diccionario describe las dos tablas propias de ScanTrue y una referencia breve a `auth.users`, administrada por Supabase. Se elaboró a partir de las migraciones 001–005 y se contrastó con las columnas del proyecto Supabase conectado el 12 de octubre de 2026.

**Cómo leer la columna «Tamaño»:** en tipos de longitud fija se indican bytes; en `varchar` y restricciones de texto, caracteres. «Variable» significa que el tipo no tiene un límite fijo declarado. `PK` = clave primaria; `FK` = clave foránea.

## ENTIDAD: ANÁLISIS

**Tabla:** `public.analisis`  
**Descripción:** almacena el texto analizado, el resultado conjunto y el estado de su registro blockchain. Cada fila pertenece a un usuario de Supabase Auth.

| KEY | Nombre | Campo | Tipo dato | Tamaño | Descripción |
| --- | --- | --- | --- | --- | --- |
| PK | Identificador de análisis | `id` | UUID | 16 bytes | Identifica de manera única el análisis. Se genera automáticamente. |
| FK | Identificador de usuario | `usuario_id` | UUID | 16 bytes | Usuario propietario; referencia `auth.users(id)`. |
| — | Fecha de análisis | `fecha` | Fecha y hora con zona (`timestamptz`) | 8 bytes | Momento de creación; por defecto toma la fecha y hora actual. |
| — | URL de origen | `url` | Texto | Hasta 2048 caracteres | Enlace opcional a la fuente del texto. |
| — | Texto analizado | `texto` | Texto | Variable | Fragmento que recibieron los modelos; admite `NULL` en registros históricos. |
| — | Hash del texto | `hash_texto` | Texto | 64 caracteres | SHA-256 del fragmento analizado, expresado en hexadecimal minúsculo. |
| — | Comparación de modelos | `comparacion` | Texto | Variable | Solo admite `coinciden`, `discrepan` o `no_disponible`. |
| — | Resultado unificado | `resultado_unificado` | JSONB | Variable | Resultado conjunto y pesos aplicados; puede ser `NULL` en registros históricos. Si existe, debe ser un objeto JSON. |
| — | Estado blockchain | `estado_blockchain` | Texto | Variable | `no_iniciado`, `pendiente`, `confirmado` o `fallido`; por defecto `pendiente`. |
| — | Hash de transacción | `hash_transaccion` | Texto | 66 caracteres | Identificador hexadecimal `0x` más 64 dígitos; admite `NULL` antes del envío. |
| — | Intentos de registro | `intentos_blockchain` | Entero | 4 bytes | Número de veces que se reclamó el análisis para registrarlo; mínimo 0 y valor inicial 0. |
| — | Próximo intento | `proximo_intento_blockchain` | Fecha y hora con zona (`timestamptz`) | 8 bytes | Momento a partir del cual el trabajador puede reintentar el registro. |
| — | Último error blockchain | `ultimo_error_blockchain` | Texto | Variable | Motivo del último fallo; admite `NULL`. |

**Relaciones:** un usuario de `auth.users` puede tener varios análisis. Al eliminar un usuario, sus análisis se eliminan en cascada. El índice `(usuario_id, fecha DESC, id DESC)` facilita el historial; un índice parcial sobre `(proximo_intento_blockchain, id)` atiende la cola blockchain.

## ENTIDAD: RESULTADO DE MODELO

**Tabla:** `public.resultados_modelo`  
**Descripción:** guarda una predicción individual de BiLSTM o mBERT para un análisis.

| KEY | Nombre | Campo | Tipo dato | Tamaño | Descripción |
| --- | --- | --- | --- | --- | --- |
| PK | Identificador de resultado | `id` | UUID | 16 bytes | Identifica de manera única la predicción. Se genera automáticamente. |
| FK | Identificador de análisis | `analisis_id` | UUID | 16 bytes | Análisis al que pertenece; referencia `public.analisis(id)`. |
| — | Modelo | `modelo` | Texto | Variable | Solo admite `bilstm` o `mbert`. |
| — | Versión del modelo | `version` | Texto | De 1 a 160 caracteres | Versión del checkpoint utilizado. |
| — | Clase predicha | `clase` | Texto | Variable | Solo admite `falsa` o `real`. |
| — | Probabilidad de falsedad | `probabilidad_falsa` | Doble precisión | 8 bytes | Valor numérico entre 0 y 1, inclusive. |
| — | Tokens leídos | `tokens_leidos` | Entero | 4 bytes | Cantidad de tokens procesados; debe ser mayor que 0. |

**Relaciones:** la función de creación actual guarda resultados de uno o dos modelos por análisis. La combinación `(analisis_id, modelo)` es única, por lo que no puede haber dos resultados del mismo modelo para el mismo análisis. Al eliminar el análisis, sus resultados se eliminan en cascada.

## ENTIDAD DE REFERENCIA: USUARIO DE SUPABASE AUTH

**Tabla:** `auth.users`  
**Descripción:** Supabase administra la identidad. Se muestran solo los campos necesarios para entender la relación con ScanTrue; las demás columnas internas quedan fuera de este diccionario.

| KEY | Nombre | Campo | Tipo dato | Tamaño | Descripción |
| --- | --- | --- | --- | --- | --- |
| PK | Identificador de usuario | `id` | UUID | 16 bytes | Identificador que referencia `public.analisis.usuario_id`. |
| — | Correo electrónico | `email` | VARCHAR | Hasta 255 caracteres | Correo de la cuenta; puede ser `NULL` para un usuario invitado. |
| — | Hash de contraseña | `encrypted_password` | VARCHAR | Hasta 255 caracteres | Hash de la contraseña cuando se utiliza acceso por contraseña; puede ser `NULL`. No es la contraseña en texto plano. |
| — | Usuario anónimo | `is_anonymous` | Booleano | 1 byte | Indica si el usuario es invitado; por defecto `false`. |
| — | Fecha de creación | `created_at` | Fecha y hora con zona (`timestamptz`) | 8 bytes | Momento de creación del usuario; la columna admite `NULL` en el esquema de Auth. |

**Vínculo con ScanTrue:** `public.analisis.usuario_id → auth.users.id`. Las políticas RLS de ScanTrue comparan `usuario_id` con `auth.uid()` para permitir consultar o borrar únicamente los análisis propios.

## Fuentes

- Esquema propio: `backend/db/migrations/001_identity_history.sql` a `005_texto_unico.sql`.
- Esquema de referencia de Auth: columnas consultadas en el proyecto Supabase conectado. Supabase administra esta tabla y puede modificar su esquema interno.
- Diseño físico y relaciones: [DISEÑO FÍSICO DE LA BASE DE DATOS](./DISENO_FISICO_BASE_DATOS.md).
