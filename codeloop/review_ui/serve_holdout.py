"""`codeloop serve-holdout`: the Phase 9 blind-labeling UI as a container entrypoint (spec section 15 step 3).

Deliberately separate from `codeloop serve`, which never holds the seal key. This entrypoint does: it decrypts the
40 sealed holdout encounters in memory with CODELOOP_SEAL_KEY, serves them blind (no predictions file exists in the
image or on the volume), and writes the coder's labels encrypted with the same key to <data>/sealed/holdout_labels.enc
on the volume, next to the append-only event store <data>/sealed/holdout_events.sqlite.

Configuration is environment-only:
  CODELOOP_SEAL_KEY                     the seal passphrase (required)
  CODELOOP_CODER_ID                     coder id recorded on every event (required)
  CODELOOP_UI_USER / CODELOOP_UI_PASS   basic-auth credentials, required on every route including /health
  CODELOOP_DATA_DIR                     writable state directory (default /data)
  CODELOOP_HOLDOUT_SRC                  where the image holds the sealed ciphertext (default /repo/holdout-seal)
  PORT                                  listen port (default 8080)

On first start the ciphertext (holdout_encounters.enc and its .meta.json) is copied from CODELOOP_HOLDOUT_SRC to
<data>/sealed so that every sealed artefact lives on the volume. /health reports counts only.
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
from codeloop.seal.crypto import ENV_KEY

SEALED_FILES = ("holdout_encounters.enc", "holdout_encounters.enc.meta.json")


class HoldoutServeConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class HoldoutServeSettings:
    coder_id: str
    data_dir: Path
    source_dir: Path
    port: int = 8080

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> HoldoutServeSettings:
        e = os.environ if env is None else env
        if not (e.get(ENV_USER) and (e.get(ENV_PASS) or e.get("CODELOOP_UI_PASSWORD"))):
            raise HoldoutServeConfigError(f"{ENV_USER} and {ENV_PASS} must be set; the served UI is never open")
        if not (e.get(ENV_KEY) or "").strip():
            raise HoldoutServeConfigError(f"{ENV_KEY} must be set for holdout labeling")
        coder = (e.get("CODELOOP_CODER_ID") or "").strip()
        if not coder:
            raise HoldoutServeConfigError("CODELOOP_CODER_ID must be set")
        return cls(
            coder_id=coder,
            data_dir=Path(e.get("CODELOOP_DATA_DIR") or "/data"),
            source_dir=Path(e.get("CODELOOP_HOLDOUT_SRC") or "/repo/holdout-seal"),
            port=int(e.get("PORT") or 8080),
        )

    @property
    def sealed_dir(self) -> Path:
        return self.data_dir / "sealed"


def stage_ciphertext(settings: HoldoutServeSettings) -> None:
    """Copy the sealed encounter ciphertext onto the volume once; refuse to start without it."""
    settings.sealed_dir.mkdir(parents=True, exist_ok=True)
    for name in SEALED_FILES:
        target = settings.sealed_dir / name
        if target.exists():
            continue
        src = settings.source_dir / name
        if not src.exists():
            raise HoldoutServeConfigError(f"{name} is neither on the volume nor under {settings.source_dir}")
        shutil.copy2(src, target)


def build_app(settings: HoldoutServeSettings, root: Path, passphrase: str) -> FastAPI:
    from codeloop.review_ui.app import ReviewSession, create_review_app

    stage_ciphertext(settings)
    paths = Paths(root, sealed_dir=settings.sealed_dir)
    session = ReviewSession(
        paths,
        batch="holdout",
        version="holdout",
        coder_id=settings.coder_id,
        holdout_labeling=True,
        passphrase=passphrase,
        store_path=settings.sealed_dir / "holdout_events.sqlite",
    )
    app = create_review_app(session, auth=False)
    started = time.time()

    @app.get("/health")
    def health() -> JSONResponse:
        labeled = sum(1 for eid in session.order if session.blind_done(eid))
        return JSONResponse(
            {
                "ok": True,
                "mode": "holdout",
                "encounters": len(session.order),
                "labeled": labeled,
                "coder_id": settings.coder_id,
                "uptime_s": int(time.time() - started),
            }
        )

    if not install_basic_auth(app, require=True):
        raise HoldoutServeConfigError("basic auth could not be installed")
    return app


def main(root: Path) -> None:
    import uvicorn

    settings = HoldoutServeSettings.from_env()
    passphrase = os.environ[ENV_KEY]
    app = build_app(settings, root, passphrase)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info", proxy_headers=True)  # noqa: S104 - container entrypoint
