"""Download only pinned tokenizer assets for Phase D, without model weights."""

import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets" / "tokenizer_mbert_cased"
if OUT.exists():
    raise FileExistsError(f"Tokenizer destination already exists: {OUT}")
REPO = "google-bert/bert-base-multilingual-cased"
revision = HfApi().model_info(REPO).sha
path = snapshot_download(
    repo_id=REPO,
    revision=revision,
    local_dir=OUT,
    allow_patterns=["config.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt", "special_tokens_map.json"],
)
with (OUT / "origin.json").open("x", encoding="utf-8") as handle:
    json.dump({"repo": REPO, "revision": revision, "path": path}, handle, indent=2)
    handle.write("\n")
print(json.dumps({"repo": REPO, "revision": revision, "path": path}))
