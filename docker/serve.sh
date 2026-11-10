#!/usr/bin/env bash
# Entry point of the llm service. MODEL=q35 (Qwen3.5-9B, thinking off) or q25 (Qwen2.5-7B-Instruct).
# CTX is shared by the 4 slots (8192 = 2048 tokens each; a headline question is about 250). NGL < 99 keeps some layers
# on the CPU when another program already uses the GPU memory.
set -euo pipefail
case "${MODEL:-q35}" in
  q35) args=(-m /models/Qwen_Qwen3.5-9B-Q4_K_M.gguf --reasoning off --chat-template-kwargs '{"enable_thinking":false}') ;;
  q25) args=(-m /models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf) ;;
  *) echo "MODEL must be q35 or q25" >&2; exit 1 ;;
esac
exec llama-server "${args[@]}" -ngl "${NGL:-99}" -c "${CTX:-8192}" -np 4 --host 0.0.0.0 --port 8089
