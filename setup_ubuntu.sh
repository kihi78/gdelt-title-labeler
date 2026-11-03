#!/usr/bin/env bash
# One-time setup on Ubuntu Server with an NVIDIA GPU: llama.cpp (CUDA build), the two study models, a Python venv.
# Everything is downloaded from the official sources and verified against fixed SHA256 values. Safe to re-run.
#   bash setup_ubuntu.sh
set -euo pipefail
cd "$(dirname "$0")"

LLAMA_TAG=b11327
LLAMA_URL=https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_TAG
LLAMA_SHA=d68288c8166c39799f15f279f73d48cbf4cc5a6eb93d2da8f3262904e44dc758        # llama-b11327-bin-ubuntu-cuda-12.8-x64.tar.gz
CUDART_SHA=7f5fcec2deaef1ddf1f6ff2d281c8e86ec219c6594a5128e0867d69ec98025f0       # cudart-llama-b11327-bin-ubuntu-cuda-12.8-x64.tar.gz
Q35_SHA=d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43
Q25A_SHA=dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db
Q25B_SHA=539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a

say() { printf '\n== %s\n' "$*"; }

fetch() {   # fetch URL DEST SHA256   (resumes, verifies, skips a file that already matches)
  local url=$1 dest=$2 sha=$3
  if [[ -f $dest ]] && [[ $(sha256sum "$dest" | cut -d' ' -f1) == "$sha" ]]; then echo "ok (already here): $dest"; return; fi
  curl -L --fail --retry 5 -C - -o "$dest" "$url"
  local got; got=$(sha256sum "$dest" | cut -d' ' -f1)
  if [[ $got != "$sha" ]]; then echo "SHA256 MISMATCH for $dest: $got (expected $sha)"; exit 1; fi
  echo "verified: $dest"
}

say "1/5 checks"
missing=()
for c in curl tar sha256sum python3 git; do command -v "$c" >/dev/null || missing+=("$c"); done
python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=("python3-venv")
if ((${#missing[@]})); then
  echo "Missing: ${missing[*]}"; echo "Install with:  sudo apt update && sudo apt install -y curl git python3-venv"; exit 1
fi
if ! command -v nvidia-smi >/dev/null || ! nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi does not work. Install the driver first:"
  echo "  sudo apt update && sudo ubuntu-drivers install && sudo reboot"
  exit 1
fi
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
cuda=$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9]*\)\.\([0-9]*\).*/\1 \2/p' | head -1)
read -r cmaj cmin <<<"$cuda"
echo "driver supports CUDA ${cmaj}.${cmin}"
if (( cmaj < 12 || (cmaj == 12 && cmin < 8) )); then
  echo "This build needs CUDA 12.8 or newer (driver 570+). Update the driver:  sudo ubuntu-drivers install  (then reboot)"; exit 1
fi

say "2/5 llama.cpp $LLAMA_TAG (CUDA 12.8 build)"
mkdir -p llama models data results dl
fetch "$LLAMA_URL/llama-$LLAMA_TAG-bin-ubuntu-cuda-12.8-x64.tar.gz" dl/llama.tar.gz "$LLAMA_SHA"
fetch "$LLAMA_URL/cudart-llama-$LLAMA_TAG-bin-ubuntu-cuda-12.8-x64.tar.gz" dl/cudart.tar.gz "$CUDART_SHA"
tar xzf dl/llama.tar.gz -C llama
tar xzf dl/cudart.tar.gz -C dl
cp -n dl/cudart-llama-$LLAMA_TAG-bin-ubuntu-cuda-12.8-x64/*.so* "llama/llama-$LLAMA_TAG/"
LD_LIBRARY_PATH="$PWD/llama/llama-$LLAMA_TAG" "llama/llama-$LLAMA_TAG/llama-server" --version 2>&1 | head -3

say "3/5 models (about 11 GB)"
HF_Q35=https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF/resolve/main
HF_Q25=https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main
fetch "$HF_Q35/Qwen_Qwen3.5-9B-Q4_K_M.gguf" models/Qwen_Qwen3.5-9B-Q4_K_M.gguf "$Q35_SHA"
fetch "$HF_Q25/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf" models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf "$Q25A_SHA"
fetch "$HF_Q25/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf" models/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf "$Q25B_SHA"

say "4/5 python"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

say "5/5 prompt fingerprint (must print: 2026-10-17a 722ec39738da7f77)"
.venv/bin/python label.py prompt-hash

echo
echo "Setup done. Put the CSV files into data/ and run:  bash run_check.sh"
