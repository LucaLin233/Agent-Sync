# 部署时用 --build-arg PASEO_BASE_IMAGE=... 固定已核对的镜像版本。
ARG PASEO_BASE_IMAGE=ghcr.io/getpaseo/paseo:latest
FROM ${PASEO_BASE_IMAGE}

# 保留官方入口的初始化流程；入口随后用 gosu 降权为 paseo。
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-yaml \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code @openai/codex
