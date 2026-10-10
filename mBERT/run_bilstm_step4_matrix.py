"""Execute the preregistered step-4 matrix sequentially on one GPU."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
SCRIPT = HERE / "train_bilstm_step4.py"
STATUS = HERE / "PASO_4_MATRIX_STATUS.json"


def completed(arm, length, seed):
    prefix = f"BILSTM_ES_{arm}_len{length}_seed{seed}_"
    for path in RUNS.glob(prefix + "*"):
        if (path / "metrics_validation.json").exists() and not (path / "error.txt").exists():
            return path
    return None


def save(status):
    temporary = STATUS.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATUS)


def main():
    # 512 is tested after the three primary lengths for each arm.
    matrix = [(arm, length, seed) for arm in ("main", "no_usmsc")
              for length in (128, 192, 256, 512) for seed in (42, 43, 44)]
    if STATUS.exists():
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        assert status["matrix"] == [list(x) for x in matrix]
    else:
        status = {"matrix": [list(x) for x in matrix], "attempts": [],
                  "created": datetime.now().isoformat(), "state": "running"}
        save(status)
    skip_512 = set()
    for arm, length, seed in matrix:
        if length == 512 and arm in skip_512:
            print("SKIP_512_OOM", arm, seed, flush=True)
            continue
        previous = completed(arm, length, seed)
        if previous:
            print("COMPLETE", arm, length, seed, previous.name, flush=True)
            continue
        started = datetime.now().isoformat()
        command = [sys.executable, str(SCRIPT), "--arm", arm, "--length", str(length), "--seed", str(seed)]
        status["current"] = {"arm": arm, "length": length, "seed": seed, "started": started}
        save(status)
        print("START", arm, length, seed, started, flush=True)
        proc = subprocess.run(command, cwd=HERE.parent, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace")
        status["attempts"].append({"arm": arm, "length": length, "seed": seed,
                                    "started": started, "finished": datetime.now().isoformat(),
                                    "returncode": proc.returncode, "output_tail": proc.stdout[-4000:]})
        status.pop("current", None)
        save(status)
        print(proc.stdout[-1200:], flush=True)
        if proc.returncode != 0:
            if length == 512 and "out of memory" in proc.stdout.lower():
                skip_512.add(arm)
                print("GPU_OOM_512", arm, flush=True)
                continue
            status["state"] = "stopped_on_error"
            save(status)
            raise RuntimeError(f"Run failed: {arm} len{length} seed{seed}")
    status["state"] = "complete" if not skip_512 else "complete_with_512_oom"
    status["skip_512_arms"] = sorted(skip_512)
    status["finished"] = datetime.now().isoformat()
    save(status)
    print("MATRIX_DONE", status["state"], flush=True)


if __name__ == "__main__":
    main()
