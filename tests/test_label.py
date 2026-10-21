import functools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import label


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        title = body["messages"][1]["content"].rsplit("Headline: ", 1)[1]
        ans = "1" if "inflation" in title.lower() or "物価" in title else "0"
        out = json.dumps({"choices": [{"message": {"content": ans}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def server(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(label, "SERVER", f"http://127.0.0.1:{srv.server_address[1]}")
    yield
    srv.shutdown()


def test_label_resume_and_keys(tmp_path, server):
    src = tmp_path / "in.csv"
    src.write_text("id,topic,title\n1,prices,Inflation hits Japan\n2,fx,物価が上がる\n3,markets,Weather today\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    assert label.main(["label", "--in", str(src), "--out", str(out), "--tag", "qwen3.5-9b", "--parallel", "2"]) == 0
    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert {r["id"]: r["ans"] for r in recs} == {"1": "1", "2": "1", "3": "0"}
    assert all(r["key"] == label.cache_key("qwen3.5-9b", r["topic"], r["title"]) for r in recs)
    label.main(["label", "--in", str(src), "--out", str(out), "--tag", "qwen3.5-9b"])   # second run asks nothing
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3


def test_keys_match_study_repository():
    import hashlib
    for tag, prefix in (("qwen2.5-7b", ""), ("qwen3.5-9b", "qwen3.5-9b|")):
        assert label.cache_key(tag, "prices", "t") == hashlib.sha256(f"{prefix}{label.PROMPT_VERSION}|prices|t".encode()).hexdigest()


def test_prompt_is_stable():
    assert label.prompt_hash() == "722ec39738da7f77"   # changes only if the prompt, topics or grammar change
