# Improvement-agent task environment (spec §13, invariant I5).
# The repository is bind-mounted by docker/compose.yaml with data/sealed/ excluded; egress goes only
# through the allowlist proxy (see docker/proxy/squid.conf).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates make && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /repo
ENV UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    HTTP_PROXY=http://proxy:3128 HTTPS_PROXY=http://proxy:3128 NO_PROXY=localhost,127.0.0.1
# dependencies are installed at container start from the mounted lockfile (see compose command)
CMD ["bash"]
