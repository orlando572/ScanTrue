# Plan de implementación del backend de ScanTrue

## Objetivo de esta entrega

Dejar una API local funcional y demostrable desde FastAPI. Debe analizar texto con los checkpoints BiLSTM y mBERT seleccionados, guardar un historial separado por identidad en PostgreSQL de Supabase, consultar métricas y registrar cada análisis terminado en una cadena EVM local. Solo se muestran predicciones reales de modelos disponibles.

## Hoja de ruta actual

1. **Integración con la extensión: implementada y comprobada.** Texto seleccionado, vista previa, detalle, resultado unificado persistido y cierre de sesión están disponibles. La migración 004 está aplicada; el contrato está en [FEATURE_INTEGRACION_FRONTEND.md](FEATURE_INTEGRACION_FRONTEND.md). La guía ya entregada a frontend está en [`../FRONTEND_CONTEXT.md`](../../frontend/docs/FRONTEND_CONTEXT.md) y no se modifica.
2. **Cierre operativo: transferencia comprobada.** Auth anónimo está habilitado; los recorridos reales cubrieron invitados, historial, eliminación, porcentajes, blockchain y transferencia a una cuenta temporal confirmada por Auth Admin. Queda por comprobar el envío y clic del correo de registro cuando termine el límite temporal de Supabase.
3. **mBERT real: implementado y comprobado operativamente.** El checkpoint, tokenizador, mapa de clases y evaluaciones del modelo seleccionado están en `mBERT/`; el adaptador del backend carga la inferencia real. La API conserva los tres espacios de porcentaje y el resultado unificado. El recorrido con Supabase y Anvil confirmó persistencia de dos predicciones, aislamiento y blockchain. La actualización del contrato para frontend está en [CAMBIO_CONTRATO_MBERT.md](CAMBIO_CONTRATO_MBERT.md).
4. **Texto único: implementado.** La migración 005 elimina el título separado de la base de datos; `POST /analisis` usa solo `texto` y `url` opcional. La extensión ya enviaba ese contrato.

## Tecnologías del backend

| Parte | Tecnología |
| --- | --- |
| API | Python y FastAPI |
| BiLSTM | PyTorch y checkpoint actual del repositorio |
| mBERT | PyTorch y Hugging Face Transformers |
| Identidad y datos | Supabase Auth y PostgreSQL de Supabase alojado |
| Blockchain local | Anvil, contrato Solidity y Web3.py |
| Hash del contenido | SHA-256 |

La API y Anvil se ejecutarán en el equipo local. Supabase requiere internet. URL, claves y rutas de modelos irán en configuración; las claves privadas y privilegiadas no se guardarán en Git.

## Funciones que deben quedar implementadas

### 1. Inferencia y comparación

- Extraer la carga e inferencia BiLSTM del script de consola a un módulo reutilizable. Cargar el checkpoint una sola vez al iniciar la API y corregir su ruta predeterminada.
- Recibir una sola cadena `texto`, con URL opcional. El titular seleccionado forma parte de esa cadena.
- Rechazar texto vacío, ilegible o insuficiente antes de inferir. Exigir 100 tokens por modelo disponible; recortar al prefijo de 512 tokens mBERT y entregar como máximo 192 tokens propios a BiLSTM. Guardar solo el prefijo analizado y explicar cuándo hubo recorte.
- Usar para cada modelo la preparación y tokenización de su entrenamiento. Conservar palabras que cambian el sentido, como las negaciones.
- Devolver clase, puntuación, versión y tokens leídos del BiLSTM. La puntuación es una salida del clasificador, no certeza factual.
- Usar el adaptador mBERT con el mismo contrato y el checkpoint seleccionado. Si falla o falta, informar `no_disponible` o `fallo` según el caso y conservar el resultado válido del otro modelo.
- Cuando ambos respondan, informar si coinciden o discrepan. La media ponderada de las salidas reales disponibles ya está implementada: mBERT 70 % y BiLSTM 30 % por defecto, con pesos configurables en el backend. Se muestra como salida para la clase falsa, no como certeza factual; la evaluación de calibración posterior no bloquea este contrato.

### 2. Identidad e historial en Supabase

- Crear el proyecto Supabase alojado y configurar PostgreSQL y Supabase Auth para usuarios anónimos y cuentas con correo y contraseña.
- Crear y versionar una migración SQL con las tablas, restricciones, índices y políticas RLS del backend. Aplicarla al proyecto Supabase antes de conectar la API.
- Crear invitados mediante Supabase Auth anónimo. Cada instalación tendrá una sesión distinta y un historial propio.
- Permitir crear una cuenta y entrar en una existente mediante Supabase Auth. Al registrarse o iniciar sesión, incorporar el historial de invitado a la cuenta después de verificar ambas identidades.
- Guardar en PostgreSQL cada análisis terminado con propietario, fecha, fragmento analizado, referencia breve, hash SHA-256 de ese fragmento, resultados y versiones de los modelos, comparación y estado blockchain. El fragmento solo estará disponible para su propietario; no enviarlo a blockchain.
- Activar RLS para que una identidad solo consulte y elimine sus análisis. La clave de servicio, necesaria para operaciones administrativas de incorporación, permanecerá únicamente en el backend.
- Listar el historial propio, abrir un análisis y eliminarlo de Supabase. Eliminar del historial no borra una transacción ya confirmada en la cadena.

#### Tablas que se crearán

Supabase Auth ya proporciona la tabla de usuarios en auth.users; no se duplicarán contraseñas ni cuentas en una tabla propia.

| Tabla | Campos principales | Relación y uso |
| --- | --- | --- |
| public.analisis | id UUID, usuario_id UUID, fecha, url, hash_texto, comparacion, estado_blockchain, hash_transaccion, texto y resultado_unificado | usuario_id referencia auth.users. Guarda cada análisis terminado y permite listar el historial del dueño. El texto de registros anteriores al cambio podrá ser NULL; el resultado unificado guarda valor, pesos, participantes y versión de la regla. |
| public.resultados_modelo | id UUID, analisis_id UUID, modelo, version, clase, probabilidad_falsa, tokens_leidos | analisis_id referencia public.analisis. Guarda una fila por modelo que produjo resultado; no se crea una predicción ficticia de mBERT. |

La migración incluirá eliminación en cascada de resultados_modelo cuando se elimine su análisis, unicidad de (analisis_id, modelo), índices para listar por usuario y fecha, y estados válidos para blockchain. RLS permitirá leer y eliminar únicamente filas propias. Para resultados_modelo, el acceso se comprobará a través del propietario del análisis. El backend hará las operaciones normales con la identidad del usuario; cualquier uso de la clave privilegiada quedará limitado al servidor y a operaciones verificadas, como incorporar un historial de invitado a una cuenta existente.

### 3. Registro blockchain local

- Crear un contrato mínimo que registre hash del texto, fecha, ID del análisis, versiones y resultados disponibles de los modelos, sin guardar la noticia completa.
- Iniciar Anvil con estado guardado para conservar las transacciones tras un reinicio.
- Tras guardar el análisis en Supabase, intentar enviar la transacción. Devolver la clasificación sin esperar su confirmación.
- Guardar los estados pendiente, confirmado o fallido y el hash de transacción. Recuperar registros pendientes tras reiniciar el backend.
- Ofrecer una consulta que compare los datos del análisis con el recibo de la transacción. Si falla Anvil, mantener la predicción y señalar la falla del registro.

### 4. Métricas y operación

- Exponer las evaluaciones disponibles de cada versión: conjunto de prueba, cantidad de ejemplos, matriz de confusión, precisión, exhaustividad y F1. No usar análisis de usuarios para calcular esas métricas.
- Documentar dependencias, variables de configuración, arranque de API y Anvil, conexión a Supabase y versión de cada checkpoint.
- Diferenciar fallas de validación, modelo, Supabase y blockchain en las respuestas. Indicar cuándo se puede repetir la solicitud.

## API prevista

| Ruta | Función |
| --- | --- |
| POST /invitados | Crear sesión anónima en Supabase Auth |
| POST /cuentas | Convertir invitado en cuenta y conservar su historial |
| POST /sesiones | Iniciar sesión e incorporar el historial de invitado |
| POST /sesiones/renovar | Renovar los tokens de la sesión actual (implementada) |
| POST /sesiones/cerrar | Revocar el token de renovación de la sesión actual |
| POST /analisis | Validar, clasificar, guardar e iniciar registro blockchain |
| GET /analisis | Listar el historial propio con `vista_previa` y `resultado_unificado` |
| GET /analisis/{id} | Consultar un análisis propio con `texto` completo y `resultado_unificado` |
| DELETE /analisis/{id} | Eliminar un análisis del historial propio |
| GET /analisis/{id}/verificacion | Ver estado y contrastar la transacción |
| GET /metricas | Consultar evaluaciones por modelo y versión |
| GET /salud | Ver estado de API, modelos, Supabase y Anvil |

La respuesta de POST /analisis separa resultados por modelo, comparación, fallas parciales, estado blockchain y `resultado_unificado` con probabilidad de falsa, pesos aplicados, modelos participantes y versión de la regla. Si ningún modelo produce una predicción válida, no se crea un análisis terminado.

### Actualización acordada para integrar el frontend (implementada)

- `POST /analisis` acepta la selección íntegra en `texto` y `url` opcional. La actualización mBERT recorta a 512 tokens propios, exige 100 tokens por modelo disponible y guarda solo el fragmento analizado; BiLSTM lee hasta 192 tokens propios. El cambio para frontend se documenta en [CAMBIO_CONTRATO_MBERT.md](CAMBIO_CONTRATO_MBERT.md).
- La migración 004 añadió `public.analisis.texto` nullable y `resultado_unificado`; la lectura del texto queda limitada al propietario. Ni blockchain ni el hash contienen el texto completo.
- El listado devuelve `vista_previa`, el detalle devuelve `texto`, y ambas respuestas incluyen `resultado_unificado`. Los registros anteriores pueden tener texto y vista previa `null`.
- `POST /sesiones/cerrar` revoca el token de renovación de la sesión actual; un JWT emitido puede seguir válido hasta vencer.
- Los recorridos reales comprobaron aislamiento entre invitados, traslado a cuenta, texto guardado y blockchain. El correo de confirmación quedó pendiente por límite temporal de Supabase.

## Orden de trabajo

### Paso 1. Preparar la inferencia BiLSTM

- Identificar el checkpoint que se usará en la demostración y corregir la ruta predeterminada que hoy apunta a otro archivo.
- Separar del script de consola las funciones para cargar el modelo, tokenizar y predecir. El backend las importará directamente y cargará el checkpoint una sola vez al arrancar.
- Usar el formato común de resultado por modelo: nombre, versión, clase, puntuación, tokens leídos y error si lo hubiera.
- **Al terminar:** una función de Python recibe texto y devuelve una predicción BiLSTM real con el checkpoint elegido.

### Paso 2. Crear la API de análisis

- Crear la aplicación FastAPI y los esquemas de entrada y salida. La solicitud acepta texto y, opcionalmente, URL.
- Validar texto antes de inferir y devolver un error claro para entradas vacías, ilegibles, insuficientes o fuera de los límites definidos.
- Implementar POST /analisis con BiLSTM y mBERT independientes, conservando el resultado válido de uno cuando el otro falle.
- Añadir GET /salud y revisar la documentación automática en /docs. En esta etapa la predicción puede ejecutarse antes de conectarla al historial; el paso 3 añadirá persistencia e identidad.
- **Al terminar:** la API clasifica texto válido y comunica errores de entrada y disponibilidad del modelo.

### Paso 3. Crear la base de datos y el historial en Supabase

- Crear el proyecto Supabase alojado y habilitar inicio anónimo y por correo en Supabase Auth.
- Escribir y aplicar una migración SQL versionada para public.analisis y public.resultados_modelo, con claves foráneas, restricciones, índices y políticas RLS.
- Conectar la API a Supabase y verificar la sesión recibida. Implementar creación de invitado, creación de cuenta e inicio de sesión.
- Guardar cada análisis terminado con su propietario, texto seleccionado y resultados; implementar listado con vista previa, detalle con texto completo y eliminación del historial propio. Conservar los registros previos sin texto al añadir el nuevo campo.
- Implementar la incorporación del historial anónimo al crear una cuenta o iniciar sesión en una existente, verificando ambas identidades antes de trasladar registros.
- **Al terminar:** invitados y cuentas pueden analizar y consultar solo sus registros; el historial persiste al reiniciar la API.

### Paso 4. Publicar métricas de evaluación

- Seleccionar los resultados de evaluación ya documentados del checkpoint BiLSTM usado por la API.
- Preparar datos legibles para GET /metricas: versión, nombre del conjunto de prueba, cantidad de ejemplos, matriz de confusión, precisión, exhaustividad, F1 y limitaciones.
- Publicar métricas de BiLSTM y mBERT solo para evaluaciones medidas y versiones exactas de sus checkpoints.
- **Al terminar:** la API muestra métricas rastreables; ninguna cifra se calcula a partir del historial de usuarios.

### Paso 5. Implementar el registro blockchain local

- Crear el contrato Solidity mínimo y desplegarlo en Anvil. Configurar Anvil para guardar y recuperar su estado después de reinicios.
- Conectar el backend con Web3.py. Después de guardar un análisis terminado en Supabase, enviar una transacción con el hash del texto y los datos mínimos del resultado, sin enviar la noticia completa.
- Guardar el estado pendiente, confirmado o fallido y el hash de la transacción. Si el proceso se interrumpe, revisar los registros pendientes al volver a iniciar.
- Implementar GET /analisis/{id}/verificacion para leer el recibo y comparar sus datos con el historial. La clasificación seguirá disponible si Anvil falla.
- **Al terminar:** un análisis genera una transacción verificable sin retrasar la respuesta de clasificación.

### Paso 6. Documentar y revisar el flujo completo

- Documentar cómo configurar Supabase, instalar dependencias, preparar variables de entorno, iniciar Anvil y levantar la API. Mantener fuera de Git las claves y credenciales.
- Recorrer desde /docs: crear invitado, analizar noticia, ver historial, consultar transacción, crear o abrir cuenta, comprobar incorporación del historial y eliminar una entrada.
- Revisar errores de entrada, modelo, Supabase y Anvil, además del tiempo hasta devolver la clasificación. Registrar qué requisitos dependen todavía de mBERT.
- **Al terminar:** otra persona del equipo puede levantar y demostrar el backend siguiendo el README.

### Paso 7. Incorporar mBERT (implementado y comprobado)

- El checkpoint, tokenizador, mapa de clases, formato de entrada y evaluaciones del modelo seleccionado se incorporaron desde `mBERT/`.
- El adaptador mBERT ejecuta inferencia independiente sobre el fragmento analizado, con su propio tokenizador; BiLSTM limita su lectura a 192 tokens.
- Responder con ambas predicciones e indicar coincidencia o discrepancia. Si una falla, conservar la predicción válida de la otra.
- Usar la regla ponderada ya versionada cuando mBERT esté disponible, y evaluar su calidad y calibración frente a cada modelo. Si se sustituye la regla, publicar una versión nueva sin reescribir resultados históricos. Medir de nuevo el tiempo total con ambos modelos.
- **Al terminar:** el recorrido real con Supabase y Anvil confirmó ambos modelos; `POST /analisis` tardó 1,21 s en esa ejecución.

## Criterio de cierre de esta entrega

Las migraciones de PostgreSQL están aplicadas en Supabase y sus tablas y políticas están documentadas. Desde la API se puede crear un invitado, analizar con los modelos disponibles, consultar el historial con vista previa y abrir el fragmento analizado de un registro propio, eliminarlo, convertir el invitado en cuenta y conservar sus registros, cerrar la sesión actual, consultar métricas y obtener una transacción local verificable. Los registros anteriores al nuevo campo pueden tener `texto: null`. El recorrido operativo de mBERT con Supabase y Anvil pasó; el registro normal con confirmación por correo sigue pendiente por el límite temporal del proveedor.
