"""GPU job worker: takes jobs from one Discord channel and runs each in a container with NO network.

Why this shape: the lab GPU machine must not be reachable from outside (no inbound port, no remote shell). The worker
only makes an outbound connection to Discord. A job is a zip with job.py (+ input files); it runs in the
gdelt-title-labeler image with --network none, a read-only root, no capabilities and only its own folder writable,
so even a job that misbehaves cannot reach the lab network or the internet. Results go back as a zip.

Accepted only from: the configured server (GUILD_ID), the jobs channel (JOBS_CHANNEL_ID), and authors in ALLOWED_USER_IDS
(the dispatcher bot) or the server's owner.

Messages in the jobs channel:
  job <id>      with one attachment <id>.zip   -> queued; result posted in the results channel as "result <id> ..."
  status                                        -> queue and running job
  cancel <id>                                   -> stop a queued or running job
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import discord
import docker

ENV = os.environ
GUILD_ID = int(ENV["GUILD_ID"])
JOBS_CHANNEL_ID = int(ENV["JOBS_CHANNEL_ID"])
RESULTS_CHANNEL_ID = int(ENV["RESULTS_CHANNEL_ID"])
ALLOWED = {int(x) for x in ENV["ALLOWED_USER_IDS"].replace(" ", "").split(",") if x}
JOBS_DIR = Path(ENV["JOBS_DIR"])            # same absolute path on the host and in this container
MODELS_DIR = ENV["MODELS_DIR"]              # host path, mounted read-only into jobs
JOBKIT_DIR = ENV["JOBKIT_DIR"]              # host path of jobbot/jobkit, mounted read-only into jobs
IMAGE = ENV.get("JOB_IMAGE", "gdelt-title-labeler:b11327")
HOST_UID = ENV.get("HOST_UID", "1000")
HOST_GID = ENV.get("HOST_GID", "1000")
MAX_ZIP = 24 * 2**20                        # attachment size
MAX_UNZIPPED = 1 * 2**30
MAX_FILES = 2000
DEFAULT_HOURS, MAX_HOURS = 6, 24
KEEP_DAYS = 3                               # job folders (inputs are publishers' text) are deleted after this
PART = 9 * 2**20                            # Discord upload limit is 10 MiB for bots in an unboosted server
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
client = discord.Client(intents=intents)
dock = docker.from_env()
queue: asyncio.Queue = asyncio.Queue()
queued: dict[str, dict] = {}
running: dict = {"id": None, "container": None, "cancel": False}


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def safe_extract(data: bytes, dest: Path) -> list[str]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise ValueError(f"too many files ({len(infos)})")
    if sum(i.file_size for i in infos) > MAX_UNZIPPED:
        raise ValueError("unzipped size over 1 GiB")
    names = []
    for i in infos:
        p = Path(i.filename)
        if p.is_absolute() or ".." in p.parts or (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"bad path in zip: {i.filename}")
        names.append(i.filename)
    dest.mkdir(parents=True)
    zf.extractall(dest)
    if not (dest / "job.py").is_file():
        raise ValueError("job.py missing at the top of the zip")
    return names


def zip_dir(src: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file() and not f.is_symlink():
                z.write(f, f.relative_to(src))
    return buf.getvalue()


def cleanup_old():
    now = time.time()
    for d in JOBS_DIR.iterdir():
        if d.is_dir() and now - d.stat().st_mtime > KEEP_DAYS * 86400 and d.name != running["id"]:
            shutil.rmtree(d, ignore_errors=True)


def run_container(job_id: str, hours: float) -> tuple[int, str]:
    d = JOBS_DIR / job_id
    out = d / "out"
    out.mkdir(exist_ok=True)
    os.chown(out, int(HOST_UID), int(HOST_GID))
    c = dock.containers.run(
        IMAGE, ["python3", "/work/in/job.py"], name=f"gpujob-{job_id}", detach=True,
        working_dir="/work/out", user=f"{HOST_UID}:{HOST_GID}",
        network_mode="none", read_only=True, tmpfs={"/tmp": "size=2g"},
        cap_drop=["ALL"], security_opt=["no-new-privileges"], pids_limit=512, mem_limit="32g", shm_size="1g",
        environment={"PYTHONPATH": "/opt/jobkit", "HOME": "/tmp", "PYTHONUNBUFFERED": "1", "JOB_ID": job_id},
        volumes={str(d / "in"): {"bind": "/work/in", "mode": "ro"}, str(out): {"bind": "/work/out", "mode": "rw"},
                 MODELS_DIR: {"bind": "/models", "mode": "ro"}, JOBKIT_DIR: {"bind": "/opt/jobkit", "mode": "ro"}},
        device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])])
    running["container"] = c
    try:
        res = c.wait(timeout=hours * 3600)
        code = res.get("StatusCode", -1)
    except Exception:
        c.kill()
        code = 124
    logs = c.logs(stdout=True, stderr=True).decode("utf-8", "replace")
    c.remove(force=True)
    (out / "_log.txt").write_text(logs, encoding="utf-8")
    return code, logs


async def runner():
    await client.wait_until_ready()
    results = client.get_channel(RESULTS_CHANNEL_ID)
    while True:
        job = await queue.get()
        job_id = job["id"]
        if queued.pop(job_id, None) is None:          # cancelled while waiting
            continue
        running.update(id=job_id, cancel=False, started=time.time())
        log("start", job_id)
        try:
            code, logs = await asyncio.to_thread(run_container, job_id, job["hours"])
        except Exception as e:                          # image missing, GPU busy, ...
            code, logs = -1, f"worker error: {e!r}"
        secs = int(time.time() - running["started"])
        if running["cancel"]:
            code = 130
        out = JOBS_DIR / job_id / "out"
        data = zip_dir(out) if out.exists() else b""
        shutil.rmtree(JOBS_DIR / job_id / "in", ignore_errors=True)   # inputs are not kept
        parts = [data[i:i + PART] for i in range(0, len(data), PART)] or [b""]
        tail = "\n".join(logs.strip().splitlines()[-15:])[-1500:]
        head = f"result {job_id} exit={code} secs={secs} parts={len(parts)} bytes={len(data)}"
        for k, p in enumerate(parts, 1):
            name = f"{job_id}.zip" if len(parts) == 1 else f"{job_id}.zip.part{k:02d}"
            files = [discord.File(io.BytesIO(p), filename=name)] if p else []
            msg = head if k == 1 else f"result-part {job_id} {k}/{len(parts)}"
            if k == 1 and tail:
                msg += f"\n```\n{tail}\n```"
            await results.send(msg, files=files)
        log("done", job_id, code, secs)
        running.update(id=None, container=None)
        await asyncio.to_thread(cleanup_old)


@client.event
async def on_ready():
    log("ready as", client.user, "allowed", sorted(ALLOWED))
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


@client.event
async def on_message(m: discord.Message):
    if m.author.id == client.user.id or m.guild is None or m.guild.id != GUILD_ID or m.channel.id != JOBS_CHANNEL_ID:
        return
    if m.author.id not in ALLOWED and m.author.id != m.guild.owner_id:     # the server owner is always allowed
        log("ignored author", m.author.id)
        return
    words = m.content.strip().split()
    if not words:
        return
    cmd = words[0].lower()
    if cmd == "status":
        r = f"running: {running['id']} ({int(time.time() - running['started'])} s)" if running["id"] else "running: -"
        await m.reply(f"{r}\nqueued: {', '.join(queued) or '-'}", mention_author=False)
    elif cmd == "cancel" and len(words) == 2:
        jid = words[1]
        if queued.pop(jid, None) is not None:
            await m.reply(f"cancelled {jid} (was queued)", mention_author=False)
        elif running["id"] == jid and running["container"] is not None:
            running["cancel"] = True
            await asyncio.to_thread(running["container"].kill)
            await m.reply(f"stopping {jid}", mention_author=False)
        else:
            await m.reply(f"no job {jid}", mention_author=False)
    elif cmd == "job" and len(words) == 2:
        jid, fresh = words[1], False
        try:
            if not ID_RE.match(jid):
                raise ValueError("id must be lowercase letters, digits and '-' (max 40)")
            if (JOBS_DIR / jid).exists() or jid in queued:
                raise ValueError("id already used; pick a new one")
            fresh = True
            if len(m.attachments) != 1 or m.attachments[0].filename != f"{jid}.zip":
                raise ValueError(f"attach exactly one file named {jid}.zip")
            if m.attachments[0].size > MAX_ZIP:
                raise ValueError("zip over 24 MiB")
            data = await m.attachments[0].read()
            names = await asyncio.to_thread(safe_extract, data, JOBS_DIR / jid / "in")
            hours = DEFAULT_HOURS
            if "job.json" in names:
                hours = float(json.loads((JOBS_DIR / jid / "in" / "job.json").read_text()).get("hours", DEFAULT_HOURS))
            hours = max(0.05, min(hours, MAX_HOURS))
        except Exception as e:
            if fresh:
                shutil.rmtree(JOBS_DIR / jid, ignore_errors=True)
            await m.reply(f"rejected: {e}", mention_author=False)
            return
        queued[jid] = {"id": jid, "hours": hours}
        await queue.put(queued[jid])
        await m.reply(f"queued {jid} ({len(names)} files, limit {hours:g} h, position {len(queued)})", mention_author=False)


async def main():
    async with client:
        task = asyncio.create_task(runner())
        try:
            await client.start(ENV["DISCORD_TOKEN"])
        finally:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
