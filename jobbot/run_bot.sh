#!/usr/bin/env bash
# Start (or restart) the GPU job worker on the lab machine.   bash jobbot/run_bot.sh   |   stop: docker rm -f gpu-jobbot
# Settings and the bot token live in ~/.config/gpu-jobbot.env (mode 600, never in Git):
#   DISCORD_TOKEN=...            (worker bot's token; paste it yourself)
#   GUILD_ID=...  JOBS_CHANNEL_ID=...  RESULTS_CHANNEL_ID=...  ALLOWED_USER_IDS=id1,id2
# The worker only connects out to Discord. Jobs run in the gdelt-title-labeler image with no network (see worker.py).
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
envf=$HOME/.config/gpu-jobbot.env
[[ -f $envf ]] || { echo "missing $envf (see jobbot/README.md)"; exit 1; }
chmod 600 "$envf"
docker image inspect gdelt-title-labeler:b11327 >/dev/null || { echo "build the labeler image first: docker compose build"; exit 1; }
mkdir -p "$repo/jobs"
docker build --pull=false -q -t gpu-jobbot:1 "$repo/jobbot"
docker rm -f gpu-jobbot >/dev/null 2>&1 || true
docker run -d --name gpu-jobbot --restart unless-stopped --env-file "$envf" \
  -e JOBS_DIR="$repo/jobs" -e MODELS_DIR="$repo/models" -e JOBKIT_DIR="$repo/jobbot/jobkit" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$repo/jobs:$repo/jobs" -v /var/run/docker.sock:/var/run/docker.sock \
  --log-opt max-size=10m --log-opt max-file=3 \
  gpu-jobbot:1 >/dev/null
sleep 5
docker logs --tail 5 gpu-jobbot
