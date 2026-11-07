"""Ejecuta un experimento del plan del BiLSTM: 3 pliegues × 3 semillas, y lo evalúa.

Uso: bilstm/.venv/bin/python bilstm/serie_comun.py B1 -- --pooling maxmedia
Las corridas ya terminadas (con predicciones.csv) no se repiten.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORRIDAS = ROOT / "datasets/comun_v1_corridas/bilstm"
PYTHON = ROOT / "bilstm/.venv/bin/python"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    nombre = sys.argv[1]
    extra = sys.argv[3:] if len(sys.argv) > 2 and sys.argv[2] == "--" else sys.argv[2:]
    carpeta = CORRIDAS / nombre
    predicciones = []
    for semilla in (42, 43, 44):
        for pliegue in ("F1", "F2", "F3"):
            salida = carpeta / f"{pliegue}_s{semilla}"
            if not (salida / "predicciones.csv").exists():
                if salida.exists():
                    for archivo in salida.iterdir():
                        archivo.unlink()
                comando = [str(PYTHON), str(ROOT / "bilstm/entrenar_comun.py"), "--pliegue", pliegue,
                           "--semilla", str(semilla), "--configuracion", nombre, "--salida", str(salida),
                           *extra]
                print(" ".join(comando), flush=True)
                subprocess.run(comando, check=True)
            predicciones.append(str(salida / "predicciones.csv"))
    (carpeta / "comando.json").write_text(json.dumps({"configuracion": nombre, "argumentos": extra}), "utf-8")
    subprocess.run([str(PYTHON), str(ROOT / "datos_comunes/evaluar_comun.py"), "--predicciones",
                    *predicciones, "--salida", str(carpeta / "evaluacion")], check=True)


if __name__ == "__main__":
    main()
