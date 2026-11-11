# Inicio rápido del backend de ScanTrue

Ejecuta los comandos desde la raíz del repositorio. El repositorio incluye el
código de la API, las migraciones, el contrato blockchain y los dos modelos de
producción: el BiLSTM B6 y BETO (clave `mbert`), con sus contratos y la
combinación calibrada (`datasets/combinacion_produccion/combinacion.json`).
Los pesos de BETO van con Git LFS: después de clonar, ejecuta `git lfs pull`.

## 1. Dependencias

La instalación comprobada usa Python 3.14, PyTorch 2.14.1, pandas 3.0.6 y
scikit-learn 1.9.1. En Linux:

```bash
python3.14 -m venv backend/.venv
backend/.venv/bin/python -m pip install torch==2.14.1 pandas==3.0.6 scikit-learn==1.9.1
backend/.venv/bin/python -m pip install -r backend/requirements.lock
```

También se necesitan `forge` y `anvil` de Foundry y el compilador `solc`
0.8.30 para el registro local. Estas herramientas no se guardan en Git.

## 2. Supabase y configuración local

Crea un proyecto Supabase y aplica en orden los cinco archivos
`backend/db/migrations/001_*.sql` a `005_*.sql`. Habilita el acceso anónimo y
el proveedor de correo y contraseña en Auth. Copia `backend/.env.example` a
`backend/.env` y completa la URL, la clave publicable y la clave secreta de
Supabase. El archivo `.env` y las claves nunca deben subirse a Git.

## 3. Anvil y API

Compila el contrato con `solc` 0.8.30 disponible en `PATH`:

```bash
forge build --root backend/blockchain --use solc
```

En una terminal inicia Anvil. Conserva `backend/.local/anvil-state.json` para
mantener los registros entre reinicios:

```bash
mkdir -p backend/.local
anvil --host 127.0.0.1 --port 8545 --chain-id 31337 \
  --state backend/.local/anvil-state.json --state-interval 5
```

Pon en `backend/.env` la clave privada de **una cuenta local de Anvil** como
`BLOCKCHAIN_PRIVATE_KEY`, nunca una clave de una red pública. En otra terminal,
despliega el contrato e inicia la API:

```bash
backend/.venv/bin/python -m backend.blockchain.deploy
backend/.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Comprueba `http://127.0.0.1:8000/salud` y abre
`http://127.0.0.1:8000/docs`. Para el recorrido completo, `/salud` debe
mostrar ambos modelos disponibles, Supabase configurado y blockchain conectada.
La extensión frontend usa esta misma dirección local.
