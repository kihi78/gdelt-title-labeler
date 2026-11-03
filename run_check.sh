#!/usr/bin/env bash
# First run on a new machine: do the two models reproduce the study's results, and how fast is the GPU?
# Needs in data/:  titles_check_1_final.csv  titles_9lang_v2.csv  titles_9lang_v2_cpu_q35.csv  (copied from the study PC)
#   bash run_check.sh        # about 10-20 minutes; results go to results/ and the summary to results/summary.txt
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
for f in titles_check_1_final.csv titles_9lang_v2.csv titles_9lang_v2_cpu_q35.csv; do
  [[ -f data/$f ]] || { echo "missing data/$f (see README: copying the CSV files)"; exit 1; }
done
mkdir -p results
{
  date -u
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  $PY label.py prompt-hash
  echo

  echo "=== Qwen3.5-9B (study CPU result: kappa 0.75, sensitivity 98%, specificity 72%)"
  bash serve.sh start q35
  SECONDS=0; $PY label.py validate --in data/titles_check_1_final.csv --out results/validate_q35.jsonl --tag qwen3.5-9b --parallel 4; echo "validate: ${SECONDS} s"
  SECONDS=0; $PY label.py label --in data/titles_9lang_v2.csv --out results/labels_9lang_q35.jsonl --tag qwen3.5-9b --parallel 4; echo "label 1610 titles: ${SECONDS} s"
  $PY label.py vs-csv --ref data/titles_9lang_v2_cpu_q35.csv --in results/labels_9lang_q35.jsonl --tag qwen3.5-9b
  bash serve.sh stop
  echo

  echo "=== Qwen2.5-7B-Instruct (study CPU result: kappa 0.64, sensitivity 80%, specificity 88%)"
  bash serve.sh start q25
  SECONDS=0; $PY label.py validate --in data/titles_check_1_final.csv --out results/validate_q25.jsonl --tag qwen2.5-7b --parallel 4; echo "validate: ${SECONDS} s"
  bash serve.sh stop
} 2>&1 | tee results/summary.txt
echo
echo "Done. Send results/summary.txt (and results/*.jsonl if asked) back."
