#!/usr/bin/env bash
# Download the two study models into models/ and check them against fixed SHA256 values (resumes; skips verified files).
#   bash fetch_models.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models data results

fetch() {   # fetch URL DEST SHA256
  local url=$1 dest=$2 sha=$3
  if [[ -f $dest ]] && [[ $(sha256sum "$dest" | cut -d' ' -f1) == "$sha" ]]; then echo "ok (already here): $dest"; return; fi
  curl -L --fail --retry 5 -C - -o "$dest" "$url"
  local got; got=$(sha256sum "$dest" | cut -d' ' -f1)
  if [[ $got != "$sha" ]]; then echo "SHA256 MISMATCH for $dest: $got (expected $sha)"; exit 1; fi
  echo "verified: $dest"
}

Q35=https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF/resolve/main
Q25=https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main
fetch "$Q35/Qwen_Qwen3.5-9B-Q4_K_M.gguf" models/Qwen_Qwen3.5-9B-Q4_K_M.gguf \
      d784ce9eda1a5a7b51e8f705a9e6310844bf4f173654d115823c775fdea56d43
fetch "$Q25/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf" models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
      dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db
fetch "$Q25/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf" models/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf \
      539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a
echo "models ready"
