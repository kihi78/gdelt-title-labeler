# gdelt-title-labeler

Small tool for judging whether a news **headline** is about a given topic (consumer prices, exchange rates, monetary
policy, stock markets) with a local open-weight LLM served by [llama.cpp](https://github.com/ggml-org/llama.cpp).
It is the labelling step of the preregistered study *"Does GDELT's theme tagging cover the same news equally across
languages?"* ([osf.io/znu3t](https://osf.io/znu3t)), published here so that the exact prompt, topic definitions and
decoding settings can be inspected and re-run.

- **No data in this repository.** Headlines are the publishers' text; they are exchanged outside Git. `.gitignore` blocks
  `*.csv`, `*.jsonl` and model files.
- One question per headline and topic. The model answers `1` or `0`, enforced by a grammar; temperature 0.
- Output is an append-only JSONL, resume-safe; the key of each answer is the same as in the study's own cache.

## Prompt (study version `2026-10-17a`)

`label.py` holds the system prompt, the user template and the four topic definitions. `python label.py prompt-hash` prints a
fingerprint (`2026-10-17a 722ec39738da7f77`); two machines that print different values are not measuring the same thing.

## Setup (Windows, NVIDIA GPU)

1. Install Python 3.11+ and `pip install -r requirements.txt`.
2. Download from the [llama.cpp release b11327](https://github.com/ggml-org/llama.cpp/releases/tag/b11327)
   `llama-b11327-bin-win-cuda-12.4-x64.zip` and `cudart-llama-bin-win-cuda-12.4-x64.zip` (use the 13.4 pair only if `nvidia-smi` reports
   CUDA 13.4 or higher; with CUDA 13.1 take 12.4). Unzip both into one folder, e.g. `llama\`.
3. Download a model (GGUF) into `models\`:
   - `Qwen_Qwen3.5-9B-Q4_K_M.gguf` (bartowski's quantisation of Qwen/Qwen3.5-9B, 6.17 GB) — the study's second model;
   - Qwen2.5-7B-Instruct Q4_K_M from `Qwen/Qwen2.5-7B-Instruct-GGUF` (two shards, 4.7 GB) — the study's first model.
   Record `Get-FileHash -Algorithm SHA256 <file>` for each file and compare it with the hash shown on the Hugging Face page.
4. Start the server (all layers on the GPU, 4 parallel slots):

```powershell
# Qwen3.5-9B: thinking must be off
.\llama\llama-server.exe -m models\Qwen_Qwen3.5-9B-Q4_K_M.gguf -ngl 99 -c 16384 -np 4 --host 127.0.0.1 --port 8089 `
    --reasoning off --chat-template-kwargs '{\"enable_thinking\":false}'

# Qwen2.5-7B-Instruct (first shard; the second is picked up automatically)
.\llama\llama-server.exe -m models\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf -ngl 99 -c 16384 -np 4 --host 127.0.0.1 --port 8089
```

(`-c` is shared between slots; 16384 gives each slot 4096 tokens, far more than a headline needs.)

## Use

```powershell
# 1. check that this machine reproduces the CPU results on the human-labelled set (file supplied separately)
python label.py validate --in titles_check_1_final.csv --out validate_q35.jsonl --tag qwen3.5-9b --parallel 4

# 2. label a file of headlines (columns: id,topic,title)
python label.py label --in titles.csv --out labels_q35.jsonl --tag qwen3.5-9b --parallel 4

# 3. compare with the earlier CPU answers (CSV with an `llm` column); small differences are possible (different floating-point arithmetic on GPU)
python label.py vs-csv --ref titles_9lang_v2_cpu_q35.csv --in labels_q35.jsonl --tag qwen3.5-9b

# 4. agreement between two label files with the same tag
python label.py compare a.jsonl b.jsonl
```

`--tag` is recorded in every key and must match the model actually loaded (`qwen2.5-7b`, `qwen3.5-9b`, or a new name for a
new model). Use a new tag for every new model or quantisation.

## Tests

`pip install pytest && pytest` (uses a fake server; no GPU needed).

## Licence

MIT (code only). Model weights keep their own licences (Qwen: Apache-2.0).
