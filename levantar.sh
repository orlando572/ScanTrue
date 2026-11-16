#!/usr/bin/env bash
# Levanta ScanTrue en local: Anvil (registro blockchain), la API y la web.
#
#   ./levantar.sh                  arranca todo y espera; Ctrl+C lo para todo
#   ./levantar.sh --sin-blockchain sin Anvil (la API queda "degradado", pero funciona)
#   ./levantar.sh --sin-web        solo Anvil y la API (para usar la extensión)
#
# Comprueba lo necesario antes de arrancar, reutiliza un servicio que ya esté
# escuchando en su puerto y deja los registros en backend/.local/logs/.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

PYTHON="$RAIZ/bilstm/.venv/bin/python"
DEPS="$RAIZ/backend/.deps"
TOOLS="$RAIZ/backend/.tools"
LOCAL="$RAIZ/backend/.local"
LOGS="$LOCAL/logs"
ESTADO_ANVIL="$LOCAL/anvil-state.json"
API_URL="http://127.0.0.1:8000"
WEB_URL="http://127.0.0.1:5174"

CON_BLOCKCHAIN=1
CON_WEB=1
for arg in "$@"; do
  case "$arg" in
    --sin-blockchain) CON_BLOCKCHAIN=0 ;;
    --sin-web) CON_WEB=0 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $arg (usa --help)" >&2; exit 2 ;;
  esac
done

verde() { printf '\033[32m%s\033[0m\n' "$*"; }
amarillo() { printf '\033[33m%s\033[0m\n' "$*"; }
fallo() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

escuchando() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

esperar() {  # esperar <nombre> <segundos> <comando de comprobación...>
  local nombre=$1 limite=$2; shift 2
  for ((i = 0; i < limite; i++)); do
    if "$@" >/dev/null 2>&1; then verde "✓ $nombre listo"; return 0; fi
    sleep 1
  done
  fallo "$nombre no respondió en ${limite}s. Mira $LOGS/"
}

# ── Comprobaciones ──────────────────────────────────────────────────
[[ -x "$PYTHON" ]] || fallo "Falta bilstm/.venv. Ver README («Instala las dependencias de Python»)."
[[ -d "$DEPS" ]] || fallo "Falta backend/.deps. Ver README («Instala las dependencias de Python»)."
[[ -f backend/.env ]] || fallo "Falta backend/.env (copia backend/.env.example y completa Supabase)."
pesos=datasets/mbert_produccion/modelo/best_model/model.safetensors
if [[ ! -f "$pesos" ]] || head -c 100 "$pesos" | grep -q "git-lfs"; then
  fallo "Los pesos de mBERT no están descargados: ejecuta «git lfs pull»."
fi
if ((CON_BLOCKCHAIN)); then
  [[ -x "$TOOLS/anvil" ]] || fallo "Falta backend/.tools/anvil (o usa --sin-blockchain)."
  if [[ ! -f "$LOCAL/contract.json" ]]; then
    fallo "Falta backend/.local/contract.json: despliega el contrato (README) o usa --sin-blockchain."
  fi
fi
if ((CON_WEB)) && [[ ! -d web/node_modules ]]; then
  amarillo "Instalando dependencias de la web…"
  npm --prefix web ci
fi
mkdir -p "$LOGS"

# ── Parada ordenada ─────────────────────────────────────────────────
PIDS=()
parar() {
  trap - INT TERM EXIT
  if ((${#PIDS[@]})); then
    echo; amarillo "Parando ScanTrue…"
    kill -TERM "${PIDS[@]}" 2>/dev/null || true  # Anvil guarda su estado al recibir TERM
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
}
trap parar INT TERM EXIT

# ── Anvil ───────────────────────────────────────────────────────────
if ((CON_BLOCKCHAIN)); then
  if escuchando 8545; then
    amarillo "• Anvil ya estaba en marcha (puerto 8545); se reutiliza."
  else
    # Sin --state la cadena sale vacía y el contrato de contract.json no existe.
    "$TOOLS/anvil" --host 127.0.0.1 --port 8545 --chain-id 31337 \
      --state "$ESTADO_ANVIL" --state-interval 5 >"$LOGS/anvil.log" 2>&1 &
    PIDS+=($!)
    esperar "Anvil" 20 escuchando 8545
  fi
fi

# ── API ─────────────────────────────────────────────────────────────
if escuchando 8000; then
  amarillo "• La API ya estaba en marcha (puerto 8000); se reutiliza."
else
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$DEPS:$RAIZ" \
    "$PYTHON" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 \
    >"$LOGS/api.log" 2>&1 &
  PIDS+=($!)
  esperar "API" 240 curl -fsS "$API_URL/salud"  # carga mBERT: puede tardar
fi

# ── Web ─────────────────────────────────────────────────────────────
if ((CON_WEB)); then
  if escuchando 5174; then
    amarillo "• La web ya estaba en marcha (puerto 5174); se reutiliza."
  else
    npm --prefix web run dev >"$LOGS/web.log" 2>&1 &
    PIDS+=($!)
    esperar "Web" 60 curl -fsS "$WEB_URL"
  fi
fi

# ── Resumen ─────────────────────────────────────────────────────────
echo
salud=$(curl -fsS "$API_URL/salud" 2>/dev/null || echo '{}')
echo "Salud de la API: $salud"
echo
verde "ScanTrue en marcha"
echo "  API:            $API_URL   (docs: $API_URL/docs)"
((CON_WEB)) && echo "  Web:            $WEB_URL"
((CON_WEB)) && echo "  Administración: $WEB_URL/admin"
echo "  Registros:      $LOGS/"
if ((${#PIDS[@]})); then
  echo; echo "Ctrl+C para parar."
  wait -n "${PIDS[@]}" || true
  fallo "Un servicio se ha parado solo. Mira $LOGS/"
fi
