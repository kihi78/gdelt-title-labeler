# gdelt-title-labeler

Small tool for judging whether a news **headline** is about a given topic (consumer prices, exchange rates, monetary
policy, stock markets) with a local open-weight LLM served by [llama.cpp](https://github.com/ggml-org/llama.cpp).
It is the labelling step of the preregistered study *"Does GDELT's theme tagging cover the same news equally across
languages?"* ([osf.io/znu3t](https://osf.io/znu3t)), published here so that the exact prompt, topic definitions and
decoding settings can be inspected and re-run.

- **No data in this repository.** Headlines are the publishers' text; they are exchanged outside Git (`.gitignore` blocks
  `*.csv`, `*.jsonl`, `data/`, `results/` and model files).
- One question per headline and topic. The model answers `1` or `0`, enforced by a grammar; temperature 0.
- Output is an append-only JSONL, resume-safe; the key of each answer is the same as in the study's own cache.
- Prompt version `2026-10-17a`; `python label.py prompt-hash` must print `2026-10-17a 722ec39738da7f77` on every machine.

## Setup (Ubuntu Server, NVIDIA GPU; tested design: RTX 4070 Ti SUPER 16 GB)

```bash
sudo apt update && sudo apt install -y git curl python3-venv     # once
nvidia-smi || { sudo ubuntu-drivers install && sudo reboot; }     # driver 570+ (CUDA 12.8+) is needed
git clone https://github.com/kihi78/gdelt-title-labeler && cd gdelt-title-labeler
bash setup_ubuntu.sh        # llama.cpp b11327 CUDA 12.8 build + 2 models (~11 GB) + venv; every download is SHA256-checked
```

Files used (all verified against the Hugging Face / GitHub hashes, and identical to the study server's files):

| File | Source | Size | SHA256 |
|---|---|---|---|
| `Qwen_Qwen3.5-9B-Q4_K_M.gguf` (bartowski's quantisation of Qwen/Qwen3.5-9B) | [bartowski/Qwen_Qwen3.5-9B-GGUF](https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF) | 6.17 GB | `d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43` |
| `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` | [Qwen/Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF) | 3.99 GB | `dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db` |
| `qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf` | same | 0.69 GB | `539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a` |

## Use

```bash
bash run_check.sh                      # first run: reproduce the study's CPU results and time the GPU (needs data/*.csv)
bash serve.sh start q35                # or q25; stop with: bash serve.sh stop
.venv/bin/python label.py label --in data/titles.csv --out results/labels_q35.jsonl --tag qwen3.5-9b --parallel 4
.venv/bin/python label.py validate --in data/titles_check_1_final.csv --out results/validate_q35.jsonl --tag qwen3.5-9b
.venv/bin/python label.py vs-csv --ref data/ref.csv --in results/labels_q35.jsonl --tag qwen3.5-9b
.venv/bin/python label.py compare a.jsonl b.jsonl
```

Input CSV for `label`: `id` (or `gkg_record_id`), `topic` (prices, fx, monetary, markets), `title`. `--tag` is recorded in every
key and must match the model actually loaded (`qwen2.5-7b`, `qwen3.5-9b`, or a new name for a new model).

## Tests

`pip install pytest requests && pytest` (uses a fake server; no GPU needed).

## Licence

MIT (code only). Model weights keep their own licences (Qwen: Apache-2.0).
