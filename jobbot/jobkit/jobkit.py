"""Helpers for job.py inside a GPU job container (importable as `import jobkit`).

The container has no network except loopback, the models read-only at /models, inputs read-only at /work/in,
and /work/out (the current directory) for results. Everything in /work/out is zipped and sent back.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request

MODELS = {
    "q35": ["-m", "/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf", "--reasoning", "off",
            "--chat-template-kwargs", '{"enable_thinking":false}'],
    "q25": ["-m", "/models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"],
}
URL = "http://127.0.0.1:8089"


class Llama:
    """with Llama("q35", ctx=8192, slots=4) as llm: llm.chat([...], grammar='root ::= "1" | "0"')"""

    def __init__(self, model: str = "q35", ctx: int = 8192, slots: int = 4, ngl: int = 99, extra: list[str] | None = None):
        self.cmd = ["llama-server", *MODELS[model], "-ngl", str(ngl), "-c", str(ctx), "-np", str(slots),
                    "--host", "127.0.0.1", "--port", "8089", *(extra or [])]
        self.proc = None

    def __enter__(self):
        self.log = open("/tmp/llama-server.log", "w")
        self.proc = subprocess.Popen(self.cmd, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(600):
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited:\n" + open("/tmp/llama-server.log").read()[-3000:])
            try:
                with urllib.request.urlopen(URL + "/health", timeout=2) as r:
                    if r.status == 200:
                        return self
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("llama-server did not become ready in 10 minutes")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=60)

    def chat(self, messages: list[dict], **params) -> str:
        body = {"messages": messages, "temperature": 0, **params}
        req = urllib.request.Request(URL + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)["choices"][0]["message"]["content"]


def gpu_info() -> str:
    return subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used",
                           "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
