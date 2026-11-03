#!/usr/bin/env bash
# Start or stop the local llama-server (127.0.0.1:8089) with the settings of the study.
#   bash serve.sh start q35     # Qwen3.5-9B (thinking off), tag qwen3.5-9b
#   bash serve.sh start q25     # Qwen2.5-7B-Instruct,       tag qwen2.5-7b
#   bash serve.sh stop
set -euo pipefail
cd "$(dirname "$0")"
BIN=llama/llama-b11327
export LD_LIBRARY_PATH="$PWD/$BIN"

stop() { pkill -x llama-server 2>/dev/null || true; sleep 2; }   # -x: exact process name only

case "${1:-}" in
  stop) stop; echo stopped ;;
  start)
    stop
    case "${2:-}" in
      q35) args=(-m models/Qwen_Qwen3.5-9B-Q4_K_M.gguf --reasoning off --chat-template-kwargs '{"enable_thinking":false}') ;;
      q25) args=(-m models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf) ;;
      *) echo "usage: bash serve.sh start q35|q25"; exit 1 ;;
    esac
    nohup "$BIN/llama-server" "${args[@]}" -ngl 99 -c 16384 -np 4 --host 127.0.0.1 --port 8089 > "server_${2}.log" 2>&1 < /dev/null &
    for _ in $(seq 1 120); do
      if curl -sf http://127.0.0.1:8089/health >/dev/null; then echo "server ready ($2)"; exit 0; fi
      sleep 2
    done
    echo "server did not become ready; see server_${2}.log"; tail -20 "server_${2}.log"; exit 1 ;;
  *) echo "usage: bash serve.sh start q35|q25 | stop"; exit 1 ;;
esac
