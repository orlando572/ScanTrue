# ScanTrue 🔎

Extensión para Chrome y Chromium que analiza texto seleccionado en páginas web. Usa una API local con dos modelos, un BiLSTM y BETO (BERT en español), cuyas probabilidades se calibran y combinan; Supabase gestiona la autenticación y el historial.

## Tecnologías 🧰

| Componente | Tecnologías |
| --- | --- |
| Extensión | JavaScript, React, Vite, Tailwind CSS y Chrome Manifest V3 |
| API | Python 3.14, FastAPI, PyTorch y Transformers |
| Base de datos y autenticación | Supabase Auth y PostgreSQL |
| Modelos | BiLSTM (B6) y BETO (M3b), calibrados y combinados 20/80 |
| Registro blockchain (opcional) | Solidity, Foundry y Anvil |

Los modelos de producción están en `datasets/bilstm_produccion/modelo/` y `datasets/mbert_produccion/modelo/` (BETO; sus pesos se descargan con Git LFS: `git lfs pull`), cada uno con su `contrato.json`. La combinación está en `datasets/combinacion_produccion/combinacion.json`. Cómo se eligieron: [docs/mejora_modelos/](docs/mejora_modelos/README.md).

## Requisitos

- Python 3.14
- Node.js 20.19.x o 22.12+
- Git LFS
- Proyecto Supabase
- Foundry y Solidity 0.8.30, si usarás el registro local en Anvil

## Base de datos 🗄️

1. Crea un proyecto en Supabase y habilita los proveedores **Anonymous** y **Email** en Authentication.
2. Ejecuta en orden las migraciones `backend/db/migrations/001_identity_history.sql` a `005_texto_unico.sql` en el SQL Editor de Supabase.
3. Copia `backend/.env.example` a `backend/.env` y completa `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` y `SUPABASE_SECRET_KEY`. Mantén las claves fuera de Git.

## Ejecutar localmente 🚀

Desde la raíz del repositorio:

1. Descarga los pesos de mBERT:

   ```bash
   git lfs install
   git lfs pull
   ```

2. Instala las dependencias de Python:

   ```bash
   python3.14 -m venv bilstm/.venv
   bilstm/.venv/bin/python -m pip install -r bilstm/requirements.txt
   bilstm/.venv/bin/python -m pip install --target backend/.deps -r backend/requirements.lock
   ```

3. Inicia la API:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend/.deps \
     bilstm/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
   ```

   La API responde en `http://127.0.0.1:8000`. Estado: `/salud`. Documentación: `/docs`.

4. Compila la extensión:

   ```bash
   npm --prefix frontend ci
   npm --prefix frontend run build
   ```

5. En `chrome://extensions`, activa el modo de desarrollador y carga la carpeta `frontend/dist` como extensión descomprimida.

## Registro blockchain local

Para usar el registro opcional, configura `BLOCKCHAIN_PRIVATE_KEY` en `backend/.env` con una cuenta local de Anvil. Compila el contrato:

```bash
forge build --root backend/blockchain --use solc
```

Inicia Anvil en una terminal:

```bash
anvil --host 127.0.0.1 --port 8545 --chain-id 31337
```

Con Anvil activo, despliega el contrato desde otra terminal:

```bash
PYTHONPATH=backend/.deps bilstm/.venv/bin/python -m backend.blockchain.deploy
```

Deja Anvil activo mientras uses la API.

La configuración incluida ejecuta la API localmente; este repositorio no define un destino de despliegue remoto para el servidor.
