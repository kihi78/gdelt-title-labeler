"""Send a job to the lab GPU worker through Discord and fetch its result (standard library only).

  python3 dispatch.py submit <job_dir> --id <id>     zip <job_dir> (must contain job.py) and post it as "job <id>"
  python3 dispatch.py wait <id> --out <dir>           poll the results channel, download and unzip the result
  python3 dispatch.py status                          ask the worker for its queue
  python3 dispatch.py cancel <id>

Settings in ~/.config/gpu-dispatch.env (mode 600): DISCORD_TOKEN (the dispatcher bot, not the worker),
JOBS_CHANNEL_ID, RESULTS_CHANNEL_ID.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/kihi78/gdelt-title-labeler, 1)"


def settings() -> dict:
    env = dict(os.environ)
    f = Path.home() / ".config" / "gpu-dispatch.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


S = settings()


def call(method: str, path: str, body: bytes | None = None, ctype: str | None = None):
    req = urllib.request.Request(API + path, data=body, method=method,
                                 headers={"Authorization": f"Bot {S['DISCORD_TOKEN']}", "User-Agent": UA})
    if ctype:
        req.add_header("Content-Type", ctype)
    for _ in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(json.load(e).get("retry_after", 2)) + 0.5)
                continue
            raise SystemExit(f"Discord API {e.code}: {e.read()[:300]!r}")
    raise SystemExit("rate limited")


def post(channel: str, content: str, filename: str | None = None, data: bytes | None = None):
    if filename is None:
        return call("POST", f"/channels/{channel}/messages", json.dumps({"content": content}).encode(), "application/json")
    b = uuid.uuid4().hex
    payload = json.dumps({"content": content, "attachments": [{"id": 0, "filename": filename}]}).encode()
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\nContent-Type: application/json\r\n\r\n").encode() \
        + payload + f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{filename}\"\r\n" \
        "Content-Type: application/zip\r\n\r\n".encode() + data + f"\r\n--{b}--\r\n".encode()
    return call("POST", f"/channels/{channel}/messages", body, f"multipart/form-data; boundary={b}")


def submit(job_dir: Path, job_id: str):
    if not re.match(r"^[a-z0-9][a-z0-9-]{0,39}$", job_id):
        raise SystemExit("id: lowercase letters, digits and '-' (max 40)")
    if not (job_dir / "job.py").is_file():
        raise SystemExit(f"{job_dir}/job.py missing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(job_dir.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(job_dir))
    data = buf.getvalue()
    if len(data) > 24 * 2**20:
        raise SystemExit(f"zip is {len(data) / 2**20:.1f} MiB; the limit is 24 MiB (Discord 25)")
    post(S["JOBS_CHANNEL_ID"], f"job {job_id}", f"{job_id}.zip", data)
    print(f"posted job {job_id} ({len(data)} bytes)")


def results(job_id: str) -> list[dict]:
    msgs = call("GET", f"/channels/{S['RESULTS_CHANNEL_ID']}/messages?limit=100")
    return sorted((m for m in msgs if re.match(rf"^result(-part)? {re.escape(job_id)}\b", m["content"])), key=lambda m: m["id"])


def fetch(job_id: str, out: Path, poll: int) -> int:
    while True:
        ms = results(job_id)
        head = next((m for m in ms if m["content"].startswith(f"result {job_id} ")), None)
        if head:
            n = int(re.search(r"parts=(\d+)", head["content"]).group(1))
            if len(ms) >= n:
                break
        time.sleep(poll)
    print(head["content"])
    data = b""
    for m in ms:
        for a in m["attachments"]:
            req = urllib.request.Request(a["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                data += r.read()
    out.mkdir(parents=True, exist_ok=True)
    if data:
        zf = zipfile.ZipFile(io.BytesIO(data))
        for i in zf.infolist():
            p = Path(i.filename)
            if p.is_absolute() or ".." in p.parts:
                raise SystemExit(f"bad path in result: {i.filename}")
        zf.extractall(out)
        print(f"{len(zf.infolist())} files -> {out}")
    return int(re.search(r"exit=(-?\d+)", head["content"]).group(1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit"); s.add_argument("job_dir"); s.add_argument("--id", required=True)
    w = sub.add_parser("wait"); w.add_argument("id"); w.add_argument("--out", required=True); w.add_argument("--poll", type=int, default=60)
    sub.add_parser("status")
    c = sub.add_parser("cancel"); c.add_argument("id")
    a = ap.parse_args(argv)
    if a.cmd == "submit":
        submit(Path(a.job_dir), a.id)
    elif a.cmd == "wait":
        return 0 if fetch(a.id, Path(a.out), a.poll) == 0 else 1
    elif a.cmd == "status":
        mine = post(S["JOBS_CHANNEL_ID"], "status")
        time.sleep(5)
        for m in call("GET", f"/channels/{S['JOBS_CHANNEL_ID']}/messages?after={mine['id']}&limit=5"):
            if (m.get("message_reference") or {}).get("message_id") == mine["id"]:
                print(m["content"])
                break
        else:
            print("no reply in 5 s (worker offline?)")
    elif a.cmd == "cancel":
        post(S["JOBS_CHANNEL_ID"], f"cancel {a.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
