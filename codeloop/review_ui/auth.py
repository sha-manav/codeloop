"""HTTP basic auth for the UIs, controlled by CODELOOP_UI_USER / CODELOOP_UI_PASS.

Both unset: no auth (local single-user use). Both set: every request must carry matching credentials.
Only one set: misconfiguration, refuse to start.
"""

from __future__ import annotations

import base64
import os
import secrets

from fastapi import FastAPI
from starlette.responses import PlainTextResponse

ENV_USER = "CODELOOP_UI_USER"
ENV_PASS = "CODELOOP_UI_PASS"
ENV_PASSWORD = "CODELOOP_UI_PASSWORD"  # legacy alias of CODELOOP_UI_PASS


class BasicAuthMiddleware:
    def __init__(self, app, user: str, password: str, realm: str = "CodeLoop"):
        self.app, self.user, self.password, self.realm = app, user, password, realm

    def _ok(self, header: bytes) -> bool:
        try:
            scheme, _, payload = header.decode("latin-1").partition(" ")
            if scheme.lower() != "basic":
                return False
            user, _, password = base64.b64decode(payload.strip()).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        return secrets.compare_digest(user, self.user) and secrets.compare_digest(password, self.password)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        if self._ok(headers.get(b"authorization", b"")):
            return await self.app(scope, receive, send)
        response = PlainTextResponse(
            "authentication required", status_code=401, headers={"WWW-Authenticate": f'Basic realm="{self.realm}"'}
        )
        await response(scope, receive, send)


def install_basic_auth(app: FastAPI, *, require: bool = False) -> bool:
    """Wrap `app` when both env vars are set; returns True when auth is active.

    `require=True` (the served entrypoint) refuses to run without credentials."""
    user = os.environ.get(ENV_USER)
    password = os.environ.get(ENV_PASS) or os.environ.get(ENV_PASSWORD)
    if not user and not password:
        if require:
            raise RuntimeError(f"{ENV_USER} and {ENV_PASS} must be set")
        return False
    if not (user and password):
        raise RuntimeError(f"set both {ENV_USER} and {ENV_PASS} (or neither)")
    app.add_middleware(BasicAuthMiddleware, user=user, password=password)
    return True
