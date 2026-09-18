"""`codeloop serve`: one deployable entrypoint for the audit and review UIs (Fly.io or any container host).

Configuration is environment-only:
  CODELOOP_UI_MODE      audit | review (required)
  CODELOOP_BATCH        batch name (review mode)
  CODELOOP_VERSION      version whose drafts are reviewed (review mode)
  CODELOOP_CODER_ID     coder id recorded on every event (review: required; audit: reviewer id, default "cpc")
  CODELOOP_DATA_DIR     writable state directory (default /data)
  CODELOOP_UI_USER / CODELOOP_UI_PASS   basic-auth credentials, required on every route including /health
  PORT                  listen port (default 8080); the app binds 0.0.0.0

All writes go under CODELOOP_DATA_DIR: review events to <data>/events/<version>_<batch>.sqlite, audit responses to
<data>/audit/spot_check_responses.jsonl (seeded from the repo copy on first start). This entrypoint never reads
CODELOOP_SEAL_KEY and never serves holdout labeling.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from codeloop.paths import Paths
from codeloop.review_ui.auth import ENV_PASS, ENV_USER, install_basic_auth

FORBIDDEN_ENV = ("CODELOOP_SEAL_KEY",)


class ServeConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServeSettings:
    mode: str
    data_dir: Path
    coder_id: str
    batch: str | None = None
    version: str | None = None
    port: int = 8080

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ServeSettings:
        e = os.environ if env is None else env
        mode = (e.get("CODELOOP_UI_MODE") or "").strip().lower()
        if mode not in ("audit", "review"):
            raise ServeConfigError("CODELOOP_UI_MODE must be 'audit' or 'review'")
        if not (e.get(ENV_USER) and (e.get(ENV_PASS) or e.get("CODELOOP_UI_PASSWORD"))):
            raise ServeConfigError(f"{ENV_USER} and {ENV_PASS} must be set; the served UI is never open")
        batch = (e.get("CODELOOP_BATCH") or "").strip() or None
        version = (e.get("CODELOOP_VERSION") or "").strip() or None
        coder = (e.get("CODELOOP_CODER_ID") or "").strip()
        if mode == "review":
            if not (batch and version and coder):
                raise ServeConfigError("review mode needs CODELOOP_BATCH, CODELOOP_VERSION and CODELOOP_CODER_ID")
            if batch == "holdout" or version == "holdout":
                raise ServeConfigError("holdout labeling is never served from this entrypoint")
        return cls(
            mode=mode,
            data_dir=Path(e.get("CODELOOP_DATA_DIR") or "/data"),
            coder_id=coder or "cpc",
            batch=batch,
            version=version,
            port=int(e.get("PORT") or 8080),
        )

    @property
    def events_path(self) -> Path:
        return self.data_dir / "events" / f"{self.version}_{self.batch}.sqlite"

    @property
    def audit_responses_path(self) -> Path:
        return self.data_dir / "audit" / "spot_check_responses.jsonl"


def build_app(settings: ServeSettings, root: Path) -> FastAPI:
    paths = Paths(root)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.mode == "review":
        from codeloop.review_ui.app import ReviewSession, create_review_app

        settings.events_path.parent.mkdir(parents=True, exist_ok=True)
        session = ReviewSession(
            paths,
            batch=settings.batch,
            version=settings.version,
            coder_id=settings.coder_id,
            store_path=settings.events_path,
        )
        app = create_review_app(session, auth=False)
    else:
        from codeloop.audit.responses import responses_path
        from codeloop.audit.ui import create_app

        target = settings.audit_responses_path
        target.parent.mkdir(parents=True, exist_ok=True)
        repo_copy = responses_path(paths)
        if not target.exists() and repo_copy.exists():
            shutil.copy2(repo_copy, target)  # seed from the committed copy on first start
        app = create_app(paths, reviewer=settings.coder_id, responses_path=target, auth=False)
    started = time.time()

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "mode": settings.mode,
                "batch": settings.batch,
                "version": settings.version,
                "uptime_s": int(time.time() - started),
            }
        )

    if not install_basic_auth(app, require=True):  # wraps every route, /health included
        raise ServeConfigError("basic auth could not be installed")
    return app


def main(root: Path) -> None:
    import uvicorn

    for name in FORBIDDEN_ENV:
        os.environ.pop(name, None)  # this process never holds the seal key
    settings = ServeSettings.from_env()
    app = build_app(settings, root)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info", proxy_headers=True)  # noqa: S104 - container entrypoint
