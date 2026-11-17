# Base is the ubuntu image already on the lab machine (the lab DNS does not resolve auth.docker.io, so no Docker Hub pull).
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && pip install --no-cache-dir --break-system-packages discord.py==2.4.0 docker==7.1.0 \
    && rm -rf /var/lib/apt/lists/*
COPY worker.py /app/worker.py
CMD ["python3", "-u", "/app/worker.py"]
