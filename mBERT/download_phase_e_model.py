"""Download the pinned official mBERT safetensors checkpoint once."""

import json
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parent
origin = json.loads((ROOT / "assets" / "tokenizer_mbert_cased" / "origin.json").read_text(encoding="utf-8"))
out = ROOT / "assets" / "model_mbert_cased"
if out.exists():
    raise FileExistsError(f"Model destination already exists: {out}")
path = snapshot_download(
    repo_id=origin["repo"], revision=origin["revision"], local_dir=out,
    allow_patterns=["config.json", "model.safetensors"],
)
with (out / "origin.json").open("x", encoding="utf-8") as handle:
    json.dump({"repo": origin["repo"], "revision": origin["revision"],
               "path": path, "format": "safetensors"}, handle, indent=2)
    handle.write("\n")
print(json.dumps({"path": path, "revision": origin["revision"]}))
