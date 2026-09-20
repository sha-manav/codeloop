# Improvement-agent task environment (spec §13, invariant I5).
# The repository is bind-mounted by docker/compose.yaml with data/sealed/ excluded; egress goes only
# through the allowlist proxy (see docker/proxy/squid.conf).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates make && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /repo
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /repo
ENV UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
# Dependencies (and the build backend for the editable install) are fetched while the image is built, when the
# network is open. Inside the task environment the only reachable host is the LLM provider, so a sync at container
# start could never download anything; it runs offline against this cache. The editable install points at /repo,
# which is the bind mount at run time.
COPY pyproject.toml uv.lock README.md ./
COPY codeloop/__init__.py codeloop/__init__.py
RUN uv sync --frozen --group dev
ENV UV_OFFLINE=1 \
    HTTP_PROXY=http://proxy:3128 HTTPS_PROXY=http://proxy:3128 NO_PROXY=localhost,127.0.0.1
CMD ["bash"]
