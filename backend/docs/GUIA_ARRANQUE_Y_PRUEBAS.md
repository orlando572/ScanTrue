# Arranque del backend y pruebas reales de ScanTrue

Esta guía se ejecuta **desde la raíz del repositorio**. La API local usa dos
modelos, Supabase alojado para sesiones e historial, y Anvil local para el
registro verificable. La extensión React para Chrome puede conectarse a
`http://127.0.0.1:8000`; su código no está en este repositorio, por lo que la
prueba conjunta con esa extensión todavía debe hacerse.

## Estado de esta instalación

El recorrido operativo anterior con Supabase y Anvil pasó: generó predicciones
reales de BiLSTM y mBERT, guardó y leyó el historial de un invitado con
aislamiento entre usuarios y verificó el evento blockchain. Aquí están los
checkpoints, dependencias, configuración local, artefacto compilado y estado de
Anvil. **Hay que iniciar Anvil y la API antes de probar desde el navegador.**
El envío y clic del correo de confirmación sigue pendiente: Supabase devolvió
`429 over_email_send_rate_limit` en el intento anterior.

## Archivos y dependencias

| Elemento | Ubicación o requisito |
| --- | --- |
| Intérprete usado en este equipo | `bilstm/.venv/bin/python` (Python 3.14.4, PyTorch 2.14.1). Debe poder importar `torch`, `numpy`, `pandas` y `sklearn` porque el código BiLSTM los usa. |
| Dependencias de API fijadas | `backend/requirements.lock`, instaladas en `backend/.deps`; `backend/requirements.txt` declara las dependencias directas. |
| BiLSTM (B6) | `datasets/bilstm_produccion/modelo/` con `contrato.json` y `modelo.pt` (36 MB). |
| BETO (clave `mbert`) | `datasets/mbert_produccion/modelo/` con `contrato.json` y `best_model/` (pesos de unos 440 MB con Git LFS; un puntero de 3 líneas no sirve: `git lfs pull`). |
| Combinación | `datasets/combinacion_produccion/combinacion.json` (temperaturas y pesos 0,2/0,8). |
| Supabase | `backend/.env` con URL, clave publicable y clave secreta; migraciones `backend/db/migrations/001_*.sql` a `005_*.sql` aplicadas en orden. Auth anónimo y correo/contraseña habilitados. |
| Cadena local | `backend/.tools/anvil`, `backend/.tools/forge`, `backend/.tools/solc-static-linux`, `backend/.local/anvil-state.json` y `backend/.local/contract.json`. |

En otra máquina basta con clonar el repositorio y ejecutar `git lfs pull` para
descargar los pesos de BETO. Para instalar Foundry y Solidity con las versiones y
sumas verificadas de este proyecto, sigue la sección «Registro verificable
local» de [README.md](../README.md). Conserva los archivos locales de estado y
despliegue existentes para no perder el vínculo con verificaciones anteriores.

Si ya existe `bilstm/.venv`, instala o actualiza **solo** las dependencias de
API dentro de `backend/.deps`:

```bash
bilstm/.venv/bin/python -m pip install --target backend/.deps -r backend/requirements.lock
```

En una instalación nueva se puede crear un entorno **dentro de `backend/`** en
lugar de modificar `bilstm/`:

```bash
python3.14 -m venv backend/.venv
backend/.venv/bin/python -m pip install torch==2.14.1 pandas==3.0.6 scikit-learn==1.9.1
backend/.venv/bin/python -m pip install --target backend/.deps -r backend/requirements.lock
```

En los comandos siguientes, sustituye `bilstm/.venv/bin/python` por
`backend/.venv/bin/python` si creaste ese entorno. Para otra plataforma o
aceleración CUDA, instala una compilación compatible de PyTorch antes de iniciar
la API.

## Configuración

Si `backend/.env` no existe, crea una copia de `backend/.env.example` dentro de
`backend/` y completa estas variables:

| Variable | Uso |
| --- | --- |
| `SUPABASE_URL` y `SUPABASE_PUBLISHABLE_KEY` | Proyecto alojado y operaciones de Auth. |
| `SUPABASE_SECRET_KEY` | Persistencia de predicciones y transferencia de historial; **solo en el backend**. |
| `BLOCKCHAIN_RPC_URL` | `http://127.0.0.1:8545` para Anvil local. |
| `BLOCKCHAIN_CHAIN_ID` | `31337` para el estado local documentado. |
| `BLOCKCHAIN_PRIVATE_KEY` | Clave de una cuenta **local de Anvil**; nunca una clave de red pública. |
| `ANALYSIS_MBERT_WEIGHT` | **Ya no se usa** (se ignora con un aviso). Los pesos salen de `datasets/combinacion_produccion/combinacion.json`. |

El proyecto Supabase usado aquí ya tiene aplicadas las migraciones 001–005.
Para otro proyecto, aplícalas en orden y habilita **Anonymous sign-ins** y el
proveedor de correo/contraseña en Authentication. No pongas claves de Supabase
ni la clave de Anvil en React, en la extensión, en Git o en este documento.

## Encender los servicios

**Terminal 1: Anvil.** Usa el estado guardado para conservar el contrato y sus
eventos. Mantén esta terminal abierta.

```bash
backend/.tools/anvil --host 127.0.0.1 --port 8545 --chain-id 31337 \
  --state backend/.local/anvil-state.json --state-interval 5 --quiet
```

**Terminal 2: API.** Si `backend/.local/contract.json` y el contrato ya existen
en el estado de Anvil, el comando de despliegue solo comprueba y reutiliza ese
contrato. Para una instalación nueva, compila antes de desplegar:

```bash
backend/.tools/forge build --root backend/blockchain \
  --use "$(pwd)/backend/.tools/solc-static-linux" --offline
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps \
  bilstm/.venv/bin/python -m backend.blockchain.deploy
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps \
  bilstm/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

El despliegue requiere `BLOCKCHAIN_PRIVATE_KEY`. Si detecta que el estado de
Anvil y el despliegue guardado no coinciden, revisa ambos archivos antes de
continuar; no sustituyas el estado ni el contrato guardado automáticamente.
La API carga ambos modelos al inicio. Consulta
`http://127.0.0.1:8000/docs` para los esquemas interactivos.

## Comprobar que está lista

Desde otra terminal:

```bash
curl -fsS http://127.0.0.1:8000/salud
curl -fsS http://127.0.0.1:8000/metricas
curl -fsS 'http://127.0.0.1:8000/metricas?modelo=mbert'
```

Para el recorrido completo, `/salud` debe informar `estado: "ok"`,
`modelos.bilstm: true`, `modelos.mbert: true`,
`transferencia_configurada: true` y `blockchain.conectada: true`. La salud
puede responder HTTP 200 con `estado: "degradado"`; en ese caso revisa sus
campos antes de probar análisis, historial o verificación.

El verificador integrado usa Supabase y Anvil **reales** a través de la API
FastAPI en proceso. Revisa su efecto antes de ejecutarlo: crea dos identidades
invitadas que permanecen en Supabase Auth, crea un análisis de prueba y elimina
ese análisis al terminar; deja el evento correspondiente en Anvil. Comprueba
modelos, mínimo de tokens, historial, aislamiento, renovación, cierre,
resultado unificado y verificación blockchain.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps \
  bilstm/.venv/bin/python -m backend.verificar_flujo
```

La variante `--email correo-de-prueba` intenta el registro con confirmación y
transferencia del historial. Requiere un buzón de prueba controlado por ti;
solicita la contraseña de forma interactiva y la cuenta queda en Supabase. Si
Auth responde 429, el backend comunica `registro_temporalmente_limitado`; ese
recorrido todavía no está confirmado mediante envío y clic reales del correo.

## Prueba conjunta con la extensión React

La extensión Chrome/Chromium Manifest V3 debe dar permiso de host **solo** a
`http://127.0.0.1:8000/*` y llamar a la API desde su service worker o una página
de la extensión. React puede usarse para su interfaz. El flujo mínimo es:

1. `POST /invitados`; conservar `access_token`, `refresh_token` y `expires_in`.
2. `POST /analisis` con `Authorization: Bearer <access_token>` y JSON
   `{ "texto": "...", "url": "https://..." }`. Enviar una selección de al menos
   100 tokens según **cada tokenizador del backend**; tratar su HTTP 422 como
   decisión final sobre suficiencia.
3. Mostrar `resultados.bilstm.probabilidad_falsa`,
   `resultados.mbert.probabilidad_falsa` y
   `resultado_unificado.probabilidad_falsa` multiplicados por 100, solo cuando
   los resultados correspondientes tengan `estado: "ok"`. Son salidas del
   clasificador para la clase falsa, no certeza factual. Mostrar
   `texto_recortado` si la API recortó el texto.
4. Consultar `GET /analisis`, `GET /analisis/{id}` y
   `GET /analisis/{id}/verificacion` con el mismo Bearer. El registro puede
   empezar `pendiente` y pasar a `confirmado`; consulta de nuevo para observar
   el cambio. Comprueba que el detalle contiene el fragmento realmente
   analizado.
5. Probar renovación con `POST /sesiones/renovar` y cierre con
   `POST /sesiones/cerrar`. Para cuenta y transferencia, consulta el contrato
   de [FRONTEND_CONTEXT.md](../../frontend/docs/FRONTEND_CONTEXT.md).

El contrato **vigente** para límites, mBERT real, `texto_recortado`, texto del
historial y métricas mBERT está en
[CAMBIO_CONTRATO_MBERT.md](historial/CAMBIO_CONTRATO_MBERT.md). Esa nota actualiza la guía
de frontend ya entregada, que conserva ejemplos anteriores a la integración
real de mBERT; los modelos y límites actuales están en
[CAMBIO_MODELOS_CALIBRADOS.md](CAMBIO_MODELOS_CALIBRADOS.md). BiLSTM lee como
máximo 192 palabras; BETO, 256 subpalabras incluidas las especiales. El frontend usa el resultado unificado del backend y
no lo recalcula.

La prueba conjunta queda completada cuando la extensión obtiene una sesión,
recibe las dos predicciones de una selección suficiente, muestra el resultado
unificado, recupera el historial propio y observa una verificación blockchain
`confirmado` con `verificado: true`. La evaluación de calidad de los modelos en
noticias inéditas y el correo de confirmación son trabajos posteriores.
