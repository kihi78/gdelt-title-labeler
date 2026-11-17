# jobbot: run GPU jobs on the lab machine without remote access to it

The lab GPU machine accepts no inbound connection. Instead a small worker on it connects **out** to a private Discord
server, picks up jobs posted in one channel, runs each one in a container **with no network**, and posts the result back.

```
home PC / always-on server                Discord (private server)               lab GPU machine
dispatch.py submit  ── job <id> + zip ──▶  #jobs   ──────────────────────────▶  worker.py (container)
dispatch.py wait    ◀── result <id> + zip ─ #results ◀──────────────────────────   └▶ job container: --network none,
                                                                                        read-only, GPU, /models ro
```

## What a job can and cannot do
- A job is a zip with `job.py` at the top (and its input files). It runs as `python3 /work/in/job.py` in the
  `gdelt-title-labeler:b11327` image (llama.cpp b11327 + Python 3), with `import jobkit` available
  (`jobkit.Llama("q35")` starts llama-server on loopback with the study's models).
- Inside: inputs read-only at `/work/in`, models read-only at `/models`, writable `/work/out` (zipped and sent back) and
  `/tmp` (2 GB). **No network** (not even the lab LAN), no Linux capabilities, `no-new-privileges`, 32 GB RAM, 512 processes,
  time limit 6 h (`job.json` `{"hours": 12}` up to 24).
- The worker obeys only the listed Discord user IDs and the server owner, in one server and one channel. Job folders are deleted after 3 days;
  inputs right after the run.
- Limits from Discord: job zip ≤ 24 MiB; results above 9 MiB are sent in parts and joined by `dispatch.py wait`.

## Lab machine (once, by someone at the machine)
```bash
cd ~/gdelt-title-labeler && git pull                     # this folder must already have models/ and the built image
install -m 600 /dev/null ~/.config/gpu-jobbot.env && nano ~/.config/gpu-jobbot.env
#   DISCORD_TOKEN=<worker bot token>
#   GUILD_ID=...  JOBS_CHANNEL_ID=...  RESULTS_CHANNEL_ID=...  ALLOWED_USER_IDS=<dispatcher bot id>   (the server owner is always allowed)
bash jobbot/setup_lab.sh                                   # first time (token prompt, enables docker at boot, starts the worker)
bash jobbot/run_bot.sh                                     # later restarts; the container restarts itself after reboots (docker --restart)
```
Stop: `docker rm -f gpu-jobbot`. Logs: `docker logs gpu-jobbot`. Update: `git pull && bash jobbot/run_bot.sh`.

## Sending jobs
```bash
python3 jobbot/dispatch.py submit jobbot/examples/gpu_check --id gpu-check-1
python3 jobbot/dispatch.py wait gpu-check-1 --out results/gpu-check-1
```
`~/.config/gpu-dispatch.env` (mode 600): `DISCORD_TOKEN=<dispatcher bot token>`, `JOBS_CHANNEL_ID`, `RESULTS_CHANNEL_ID`.

Never put tokens in Git. If a token leaks, reset it in the Discord Developer Portal (Bot → Reset Token) and update the env file.
