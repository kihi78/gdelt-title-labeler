# llama.cpp b11327 (the build used in the study) with its official CUDA 12.8 binaries, plus label.py.
# The official ghcr.io images skip b11327, so the release tarballs are installed here and checked against their SHA256.
FROM ubuntu:24.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 python3 python3-requests \
 && rm -rf /var/lib/apt/lists/*

ARG LLAMA_TAG=b11327
ARG LLAMA_SHA=d68288c8166c39799f15f279f73d48cbf4cc5a6eb93d2da8f3262904e44dc758
ARG CUDART_SHA=7f5fcec2deaef1ddf1f6ff2d281c8e86ec219c6594a5128e0867d69ec98025f0
RUN set -eux; cd /tmp; \
    base=https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_TAG}; \
    curl -fsSL --retry 10 --retry-all-errors --connect-timeout 20 --speed-limit 50000 --speed-time 30 -o llama.tgz  ${base}/llama-${LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz; \
    curl -fsSL --retry 10 --retry-all-errors --connect-timeout 20 --speed-limit 50000 --speed-time 30 -o cudart.tgz ${base}/cudart-llama-${LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz; \
    echo "${LLAMA_SHA}  llama.tgz" | sha256sum -c -; \
    echo "${CUDART_SHA}  cudart.tgz" | sha256sum -c -; \
    tar xzf llama.tgz -C /opt && mv /opt/llama-${LLAMA_TAG} /opt/llama; \
    tar xzf cudart.tgz && cp cudart-llama-${LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64/*.so* /opt/llama/; \
    rm -rf /tmp/*

ENV LD_LIBRARY_PATH=/opt/llama PATH=/opt/llama:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
COPY label.py docker/serve.sh ./
