"""Time a few mBERT CUDA updates to diagnose training throughput."""

import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from phase_d_data import load_manifest, load_rows


print("threads_before", torch.get_num_threads(), "cuda", torch.cuda.is_available(), flush=True)
torch.set_num_threads(4)
print("threads_after", torch.get_num_threads(), flush=True)
tokenizer = AutoTokenizer.from_pretrained(load_manifest()["tokenizer_local_path"], local_files_only=True)
rows = load_rows("es_train")[:4]
inputs = tokenizer([row["title"] for row in rows], [row["body"] for row in rows],
                   truncation="only_second", max_length=128, padding="max_length",
                   return_tensors="pt")
inputs["labels"] = torch.tensor([row["label"] for row in rows])
inputs = {key: value.cuda() for key, value in inputs.items()}
model = AutoModelForSequenceClassification.from_pretrained(
    "mBERT/assets/model_mbert_cased", num_labels=2, local_files_only=True
).cuda().train()
optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)
print("device", next(model.parameters()).device, "shape", inputs["input_ids"].shape, flush=True)
for i in range(3):
    torch.cuda.synchronize()
    start = time.perf_counter()
    optimizer.zero_grad(set_to_none=True)
    with torch.autocast("cuda", dtype=torch.bfloat16):
        loss = model(**inputs).loss
    loss.backward()
    optimizer.step()
    torch.cuda.synchronize()
    print("step", i + 1, "seconds", round(time.perf_counter() - start, 3),
          "loss", round(loss.item(), 4), "peak_gb", round(torch.cuda.max_memory_allocated() / 2**30, 3), flush=True)
