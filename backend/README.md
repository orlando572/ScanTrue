# Backend de ScanTrue

## Arquitectura

La API organiza el flujo en capas: rutas HTTP reciben solicitudes, esquemas
definen sus contratos, servicios implementan los casos de uso y adaptadores
conectan modelos y servicios externos. La API no accede directamente a los
modelos ni a Supabase.

```text
backend/
├── app.py                    # Arranque y composición de dependencias
├── api/routes.py             # Endpoints HTTP
├── schemas/                  # Validación y contratos JSON
├── services/                 # Casos de uso: análisis, cuentas e historial
├── models/                   # Adaptadores de inferencia BiLSTM y mBERT
├── repositories/             # Acceso a datos y Supabase
├── db/migrations/            # Migraciones SQL versionadas y RLS
├── blockchain/contracts/     # Contrato Solidity
├── metrics/                  # Métricas fijas por versión de modelo
├── core/                     # Configuración y dependencias compartidas
└── requirements.txt
```

## Tecnologías

- **Python, FastAPI y Pydantic** para la API, validación y documentación OpenAPI.
- **PyTorch y Transformers** para inferencia de un checkpoint BiLSTM y un
  checkpoint mBERT seleccionados.
- **Supabase Auth y PostgreSQL** para identidad e historial. Las migraciones SQL
  definen tablas, índices y políticas RLS.
- **Solidity, Foundry Anvil y Web3.py** para el registro verificable local.
- **SHA-256** para identificar el fragmento analizado; ese mismo texto se
  conserva en Supabase para el historial del propietario y nunca se envía a blockchain.

Las claves se cargarán desde variables de entorno; nunca se versionarán claves
privilegiadas ni archivos `.env`. Cuando crees el proyecto, copia
`backend/.env.example` a `backend/.env` si aún no existe y completa los valores
que falten. La clave secreta se usa para guardar predicciones reales y para
incorporar historial entre identidades.

## Tareas de implementación

1. **Inferencia — lista (actualizada el 11 nov 2026):** carga el BiLSTM **B6** y
   **BETO M3b** (clave interna `mbert`) según sus contratos
   (`datasets/{bilstm,mbert}_produccion/modelo/contrato.json`), verifica sus SHA-256,
   calibra cada probabilidad con su temperatura y combina los dos modelos según
   `datasets/combinacion_produccion/combinacion.json` (80 % BETO + 20 % BiLSTM).
   Detalle en [docs/CAMBIO_MODELOS_CALIBRADOS.md](docs/CAMBIO_MODELOS_CALIBRADOS.md).
2. **API de análisis — lista:** exige 100 tokens a cada modelo disponible;
   BETO lee hasta 256 subpalabras y BiLSTM hasta 192 palabras;
   distingue errores de entrada e inferencia y comunica la disponibilidad.
3. **Identidad e historial — código implementado:** Auth anónimo y por correo,
   tablas con RLS, historial propio e incorporación de registros del invitado.
   El texto y la vista previa cuentan con la migración 004 aplicada.
4. **Métricas — implementadas:** `GET /metricas` expone BiLSTM y
   `GET /metricas?modelo=mbert` expone BETO, con la validación por fuente.
5. **Blockchain — comprobada localmente:** contrato, cola durable, reintentos,
   estado de transacción y endpoint de verificación. El recorrido con invitado
   confirmó un análisis real en Anvil.
6. **Integración frontend — código y esquema preparados:** resultado unificado ponderado,
   texto y vista previa de historial, y cierre de la sesión actual. La migración
   004 está aplicada al proyecto conectado y pasó el recorrido con invitados.
7. **Texto único — implementado:** `POST /analisis` recibe `texto` y `url`
   opcional; la migración 005 retira la columna y las RPC con título separado.
8. **Cierre operativo — parcial:** pasaron el recorrido de invitados y la
   transferencia a una cuenta temporal confirmada por Auth Admin. El envío del
   correo de confirmación espera que se restablezca el límite de Supabase.

Los pesos de BETO (`datasets/mbert_produccion/modelo/best_model/model.safetensors`,
440 MB) van con Git LFS: tras clonar, `git lfs pull`. Si no cargan, la API informa
`no_disponible` y el BiLSTM continúa funcionando. Los modelos de octubre se conservan,
sin uso, en `datasets/{bilstm,mbert}_produccion/archivo_octubre/`.

## Métricas de evaluación

`GET /metricas` es público y funciona sin sesión, Supabase ni inferencia. Devuelve
las métricas por artículo del BiLSTM B6 con validación dejando una fuente fuera:
global (1.568 artículos) y para cada fuente no vista (v1, FakeDeS, Polyglot).
`GET /metricas?modelo=mbert` publica lo mismo para BETO. Cada registro incluye su
fuente, matriz de confusión, exactitud, precisión, recall y F1 para la clase falsa
y F1 macro. Las filas de la matriz son etiquetas reales y las columnas son
predicciones; ambos ejes usan el orden `falsa`, `real`. Los catálogos
(`backend/metrics/evaluaciones.json` y `mbert_evaluaciones.json`) se generan con
`datos_comunes/publicar_metricas.py`; los de octubre quedan en
`backend/metrics/archivo_octubre/`. Incluyen también la prueba congelada, evaluada una sola vez
(toda y solo FalleDesinfo, la única fuente nueva); ver
[docs/mejora_modelos/05_PRUEBA_CONGELADA.md](../docs/mejora_modelos/05_PRUEBA_CONGELADA.md).

## Registro verificable local

El contrato de `backend/blockchain/contracts/ScanTrueRegistry.sol` registra un
evento con ID, fecha, SHA-256 del texto, comparación y resultados reales de los
modelos. No recibe el texto, titular, URL ni identidad del usuario. La clave que
firma permanece en `backend/.env`; usa **solo una cuenta de Anvil**, nunca una
clave de una red pública. `backend/.local/contract.json` guarda dirección, ABI y
bloque de despliegue, sin clave privada. La migración
`backend/db/migrations/003_blockchain_registry.sql` agrega la cola durable y
quedó aplicada al proyecto Supabase conectado como `blockchain_registry`.

En este equipo, Foundry 1.8.5 y Solidity 0.8.30 están en `backend/.tools/`.
La carpeta está excluida de Git. Para otra instalación Linux x86_64, descarga
los binarios oficiales con estas versiones fijadas desde la raíz:

```bash
mkdir -p backend/.tools
curl -fL https://github.com/foundry-rs/foundry/releases/download/v1.8.5/foundry_v1.8.5_linux_amd64.tar.gz \
  -o backend/.tools/foundry_v1.8.5_linux_amd64.tar.gz
echo '6c66ffcc55fa4249197721baa3098bc208014ea1d8aa04b2ed50ac6bccffb226  backend/.tools/foundry_v1.8.5_linux_amd64.tar.gz' | sha256sum -c -
tar -xzf backend/.tools/foundry_v1.8.5_linux_amd64.tar.gz -C backend/.tools
curl -fL https://github.com/argotorg/solidity/releases/download/v0.8.30/solc-static-linux \
  -o backend/.tools/solc-static-linux
echo 'f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7  backend/.tools/solc-static-linux' | sha256sum -c -
chmod +x backend/.tools/solc-static-linux
```

Compila el contrato e inicia Anvil con estos comandos:

```bash
mkdir -p backend/.local
backend/.tools/forge build --root backend/blockchain \
  --use "$(pwd)/backend/.tools/solc-static-linux" --offline
backend/.tools/anvil --host 127.0.0.1 --port 8545 --chain-id 31337 \
  --state backend/.local/anvil-state.json --state-interval 5 --quiet
```

Deja Anvil ejecutándose en su propia terminal. En `backend/.env` configura
`BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545`, `BLOCKCHAIN_CHAIN_ID=31337` y
`BLOCKCHAIN_PRIVATE_KEY` con la clave de **una cuenta local de Anvil**. En otra
terminal, despliega el contrato una vez y después inicia la API:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps bilstm/.venv/bin/python -m backend.blockchain.deploy
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps bilstm/.venv/bin/python -m uvicorn backend.app:app --reload
```

No borres el estado de Anvil ni el archivo de despliegue si deseas conservar
las verificaciones anteriores. Si el contrato desaparece de la cadena, el
script de despliegue exige revisar el estado antes de crear uno nuevo.

Tras guardar un análisis, `POST /analisis` devuelve
`estado_blockchain: pendiente` sin esperar el recibo. Un trabajador reclama registros de Supabase,
envía la transacción, guarda su hash y comprueba el evento en rondas posteriores.
Reintenta errores temporales y recupera registros pendientes al reiniciar la
API. `GET /analisis/{id}/verificacion` requiere la sesión del dueño y responde
con `estado_blockchain`, `hash_transaccion`, `verificado` (`true`, `false` o
`null`) y `detalle`. La eliminación del historial no borra transacciones ya
confirmadas en Anvil. `GET /salud` muestra si la cadena está configurada y
conectada.

## Arranque de la API

Desde la raíz del repositorio, configura `backend/.env` con la URL del proyecto,
la clave publicable y una clave secreta de Supabase. El archivo local tiene
las tres variables; conserva `SUPABASE_SECRET_KEY` en el backend, sin compartirla
ni subirla a Git. En el proyecto conectado,
las migraciones `backend/db/migrations/001_identity_history.sql`,
`backend/db/migrations/002_restrict_analysis_writes.sql`,
`backend/db/migrations/003_blockchain_registry.sql`,
`backend/db/migrations/004_frontend_contract.sql` y
`backend/db/migrations/005_texto_unico.sql` quedaron aplicadas.
Para otra instalación, aplica las cinco en orden. Habilita **Anonymous sign-ins**
y el registro por correo y contraseña en **Authentication > Providers**. El 10
de octubre de 2026, Auth anónimo quedó habilitado y el recorrido con invitados
pasó. La confirmación de correo sigue activa; la transferencia a cuenta aún
requiere un correo de prueba confirmable.

Después ejecuta:

```bash
bilstm/.venv/bin/python -m pip install --target backend/.deps -r backend/requirements.lock
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps bilstm/.venv/bin/python -m uvicorn backend.app:app --reload
```

La instalación local de dependencias se guarda en `backend/.deps`, que está
excluida de Git. El entorno `bilstm/.venv` debe existir y contener PyTorch y
las dependencias del modelo. La documentación interactiva está en `/docs`.

`POST /invitados` crea una sesión anónima y devuelve tokens de acceso y
renovación. Conserva ambos tokens en el cliente. `POST /sesiones/renovar` recibe
`refresh_token` para obtener un nuevo acceso cuando expire el anterior.
`POST /sesiones/cerrar` requiere el Bearer actual, revoca la renovación de esa
sesión y responde `{ "cerrada": true }`; otras sesiones conservan su estado.
El JWT de acceso actual puede seguir válido hasta su vencimiento.

`POST /analisis` requiere `Authorization: Bearer <access_token>`. Acepta `texto`
obligatorio y `url` opcional. La URL solo sirve de referencia: la API no la
descarga. El titular forma parte de `texto` si el usuario lo seleccionó;
enviar un campo `titulo` separado devuelve 422. La respuesta tiene este
formato (con valores de ejemplo):

```json
{
  "resultados": {
    "bilstm": {
      "modelo": "bilstm",
      "estado": "ok",
      "version": "comun_v1.1_B6_20261107",
      "clase": "falsa",
      "probabilidad_falsa": 0.62,
      "tokens_leidos": 120,
      "error": null
    },
    "mbert": {
      "modelo": "mbert",
      "estado": "ok",
      "version": "comun_v1.1_M3b_20261111",
      "clase": "falsa",
      "probabilidad_falsa": 0.70,
      "tokens_leidos": 180,
      "error": null
    }
  },
  "resultado_unificado": {
    "probabilidad_falsa": 0.684,
    "modelos_utilizados": ["bilstm", "mbert"],
    "pesos_aplicados": {"bilstm": 0.2, "mbert": 0.8},
    "version_regla": "media_ponderada_v1",
    "version_combinacion": "comun_v1.1_conjunta_20261111"
  },
  "comparacion": "coinciden",
  "nota": "Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.",
  "id": "d7b9b1fb-0b62-4c4a-960e-5590cd43dd70",
  "estado_blockchain": "pendiente",
  "texto_recortado": false
}
```

`probabilidad_falsa` es la probabilidad calibrada (temperatura del contrato) de
la clase falsa, no una medida de certeza factual. Cuando dos modelos produzcan predicciones,
`comparacion` será `coinciden` o `discrepan`. Si uno falla, se conserva el
resultado válido y el otro indica `fallo`. Si ninguno responde, la API devuelve
503. El resultado unificado usa los modelos reales disponibles: con uno solo,
su peso aplicado es 1; con ambos, se combinan sus logits calibrados con BETO 0,80
y BiLSTM 0,20: `sigmoide(0,2 · logit(p_bilstm) + 0,8 · logit(p_beto))`. Los pesos
y temperaturas salen de la calibración conjunta
([docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md](../docs/mejora_modelos/04_CALIBRACION_CONJUNTA.md));
`ANALYSIS_MBERT_WEIGHT` ya no se usa. `version_regla` sigue siendo
`media_ponderada_v1` porque la base de datos solo acepta ese valor;
`version_combinacion` identifica la combinación aplicada. Cada respuesta válida guarda en Supabase el
propietario, fragmento analizado, SHA-256 de ese mismo fragmento,
referencia opcional, predicciones y resultado unificado con pesos aplicados.

`GET /analisis?limit=20&offset=0` lista el historial propio con
`vista_previa` de hasta 160 caracteres y `resultado_unificado`; `GET
/analisis/{id}` abre el fragmento analizado en `texto` y `DELETE /analisis/{id}` la elimina junto
con sus predicciones. Un ID ajeno responde 404. La lectura y eliminación usan
el JWT del usuario y las políticas RLS. La
creación usa la clave secreta solo después de verificar la sesión y ejecutar
el modelo; un cliente no puede insertar predicciones directamente. `GET
/salud` comunica disponibilidad de modelos y configuración de Supabase.

`POST /cuentas` recibe `correo` y `contrasena` con el token del invitado en
`Authorization`. Si Supabase exige confirmar el correo, responde
`pendiente_confirmacion`: conserva la sesión invitada, confirma el correo y
luego inicia sesión. `POST /sesiones` recibe las mismas credenciales; para
incorporar el historial invitado, envía además `X-Guest-Token` con el token de
acceso vigente del invitado. La API verifica ambas identidades antes de
trasladar los registros. Si el registro devuelve una sesión de cuenta de
inmediato, el traslado ocurre en `POST /cuentas`. La clave secreta permanece
en el backend.

Si Supabase limita temporalmente el registro, `POST /cuentas` devuelve HTTP 429
con `codigo: registro_temporalmente_limitado`; el cliente puede reintentar más
tarde sin perder la sesión invitada. La transferencia a una cuenta ya activa
se comprobó con una cuenta temporal confirmada por Auth Admin. El registro con
envío y clic del correo no pudo comprobarse porque Supabase devolvió
`over_email_send_rate_limit`.

El mínimo operativo de 100 tokens se exige a cada modelo disponible con su
propio tokenizador. BETO lee hasta 256 subpalabras, incluidos sus tokens
especiales, y BiLSTM hasta 192 palabras. La API conserva el prefijo más largo de
los dos (cada modelo recorta dentro de él lo suyo) y responde
`texto_recortado: true` si el texto lo excede. El historial y `hash_texto` guardan
ese mismo prefijo. Si falta el tokenizador de BETO, la degradación usa solo BiLSTM
y guarda sus primeras 192 palabras. El mínimo es una decisión operativa, no una mejora de precisión
demostrada.

## Verificación operativa

Con Anvil iniciado, el contrato desplegado y Auth anónimo habilitado, ejecuta
desde la raíz:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps \
  bilstm/.venv/bin/python -m backend.verificar_flujo
```

El recorrido crea dos invitados, comprueba la validación de 100 tokens, el
aislamiento del historial, el texto y su vista previa, el resultado unificado,
la renovación y cierre de sesión, las dos clasificaciones reales y la confirmación
blockchain. También comprueba las respuestas de degradación
de modelo, Supabase y Anvil. Mide el tiempo de `POST /analisis` y elimina
únicamente el análisis de prueba que creó. No muestra tokens ni claves.

Para comprobar también registro y transferencia, añade `--email` con una
dirección de prueba propia que puedas confirmar. El programa solicita la
contraseña de esa cuenta sin mostrarla y se detiene mientras confirmas el
correo. Tras pulsar Enter inicia sesión, comprueba la incorporación del
historial y elimina el análisis de prueba. La cuenta creada permanece en
Supabase; usa una dirección y contraseña reservadas para esta verificación.
