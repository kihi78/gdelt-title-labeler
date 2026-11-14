# Smoke test: GPU visible, no network, model answers.  python3 dispatch.py submit jobbot/examples/gpu_check --id gpu-check-1
import json
import socket
import time

import jobkit

info = {"gpu": jobkit.gpu_info()}
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3)
    info["network"] = "REACHABLE (should not be)"
except OSError:
    info["network"] = "none (as intended)"
t = time.time()
with jobkit.Llama("q35", ctx=2048, slots=1) as llm:
    info["load_s"] = round(time.time() - t, 1)
    t = time.time()
    info["answer"] = llm.chat([{"role": "user", "content": "Is 'rice prices rise again' about consumer prices? Answer 1 or 0."}],
                              max_tokens=2, grammar='root ::= "1" | "0"')
    info["answer_s"] = round(time.time() - t, 2)
print(json.dumps(info, ensure_ascii=False, indent=1))
open("gpu_check.json", "w").write(json.dumps(info, ensure_ascii=False, indent=1))
