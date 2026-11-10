#!/usr/bin/env bash
# First run on a new machine: do the two models reproduce the study's results, and how fast is the GPU?
# Needs in data/:  titles_check_1_final.csv  titles_9lang_v2.csv  titles_9lang_v2_cpu_q35.csv  (copied from the study PC)
#   bash run_check.sh          # about 10-20 minutes; summary in results/summary.txt
# If another program holds GPU memory and less than ~8 GB is free:  NGL=24 bash run_check.sh  (part of the model on the CPU)
set -euo pipefail
cd "$(dirname "$0")"
export HOST_UID=${SUDO_UID:-$(id -u)} HOST_GID=${SUDO_GID:-$(id -g)}
for f in titles_check_1_final.csv titles_9lang_v2.csv titles_9lang_v2_cpu_q35.csv; do
  [[ -f data/$f ]] || { echo "missing data/$f (see README)"; exit 1; }
done
for f in Qwen_Qwen3.5-9B-Q4_K_M.gguf qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf; do
  [[ -f models/$f ]] || { echo "missing models/$f (run: bash fetch_models.sh)"; exit 1; }
done
mkdir -p results
free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
if (( free < 8000 )) && [[ ${NGL:-99} == 99 ]]; then
  echo "Only ${free} MiB of GPU memory is free; the 9B model needs about 8000 MiB. GPU users now:"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
  echo "Either wait until the other program frees memory, or run:  NGL=24 bash run_check.sh"
  exit 1
fi

lab() { docker compose run --rm -T labeler "$@"; }
serve() {   # serve q35|q25
  MODEL=$1 docker compose up -d --wait llm
}

docker compose build
{
  date -u
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free --format=csv,noheader
  echo "NGL=${NGL:-99}"
  lab prompt-hash
  echo

  echo "=== Qwen3.5-9B (study CPU result: kappa 0.75, sensitivity 98%, specificity 72%)"
  serve q35
  SECONDS=0; lab validate --in data/titles_check_1_final.csv --out results/validate_q35.jsonl --tag qwen3.5-9b --parallel 4; echo "validate: ${SECONDS} s"
  SECONDS=0; lab label --in data/titles_9lang_v2.csv --out results/labels_9lang_q35.jsonl --tag qwen3.5-9b --parallel 4; echo "label 1610 titles: ${SECONDS} s"
  lab vs-csv --ref data/titles_9lang_v2_cpu_q35.csv --in results/labels_9lang_q35.jsonl --tag qwen3.5-9b
  docker compose down
  echo

  echo "=== Qwen2.5-7B-Instruct (study CPU result: kappa 0.64, sensitivity 80%, specificity 88%)"
  serve q25
  SECONDS=0; lab validate --in data/titles_check_1_final.csv --out results/validate_q25.jsonl --tag qwen2.5-7b --parallel 4; echo "validate: ${SECONDS} s"
  docker compose down
} 2>&1 | tee results/summary.txt
echo
echo "Done. Send results/summary.txt back (and results/*.jsonl if asked)."
