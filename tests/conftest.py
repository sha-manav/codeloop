from __future__ import annotations

import pytest

from codeloop.seal import crypto


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    """Use a cheap scrypt cost in tests; production parameters are exercised once in test_crypto."""
    monkeypatch.setattr(crypto, "KDF_PARAMS", {"n": 2**12, "r": 8, "p": 1, "length": 32})
    monkeypatch.delenv(crypto.ENV_KEY, raising=False)
