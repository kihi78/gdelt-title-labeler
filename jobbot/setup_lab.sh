#!/usr/bin/env bash
# One-time setup of the GPU job worker on the lab machine (run it yourself on that PC, from the repo root):
#   git pull && bash jobbot/setup_lab.sh
# What it does: checks docker/GPU/models, enables docker at boot (so the bot comes back after a reboot),
# writes ~/.config/gpu-jobbot.env (token read hidden from the keyboard, never echoed), starts the worker,
# and prints how to verify.  Re-running is safe (keeps the existing env file unless you answer y).
set -euo pipefail
cd "$(dirname "$0")/.."
envf=$HOME/.config/gpu-jobbot.env

command -v docker >/dev/null || { echo "docker is not installed"; exit 1; }
docker info >/dev/null 2>&1 || { echo "cannot talk to docker (add yourself to the docker group or run with sudo)"; exit 1; }
nvidia-smi -L || { echo "no GPU visible"; exit 1; }
docker image inspect gdelt-title-labeler:b11327 >/dev/null 2>&1 || { echo "building the labeler image (docker compose build)"; docker compose build; }
ls models/*.gguf >/dev/null 2>&1 || echo "WARNING: no models/*.gguf found; jobs that need a model will fail"

# Start docker at boot; the worker container has --restart unless-stopped, so it follows.
if [[ $(systemctl is-enabled docker 2>/dev/null || true) != enabled ]]; then
  echo "enabling docker at boot (sudo asks for your password)"
  sudo systemctl enable docker
fi

write_env=y
if [[ -f $envf ]]; then read -rp "$envf exists. Overwrite? [y/N] " write_env; fi
if [[ $write_env == y ]]; then
  mkdir -p "$(dirname "$envf")"
  read -rsp "Worker bot token (hidden, paste then Enter): " tok; echo
  umask 077
  {
    echo "DISCORD_TOKEN=$tok"
    echo "GUILD_ID=1571236116278018182"
    echo "JOBS_CHANNEL_ID=1571236185764925540"
    echo "RESULTS_CHANNEL_ID=1571236307424772116"
    echo "ALLOWED_USER_IDS=1571238258946478281"
  } > "$envf"
  chmod 600 "$envf"
  echo "saved ($(printf %s "$tok" | wc -c) characters)"
  unset tok
fi

bash jobbot/run_bot.sh
echo
echo "restart policy: $(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' gpu-jobbot)   docker at boot: $(systemctl is-enabled docker)"
echo "After a reboot check:  docker ps --filter name=gpu-jobbot   and   docker logs --tail 5 gpu-jobbot"
