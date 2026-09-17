"""Sealed-store encryption: AES-256-GCM with a key derived by scrypt from CODELOOP_SEAL_KEY.

File layout: `<name>.enc` = MAGIC || ciphertext (GCM tag included) and a sidecar
`<name>.enc.meta.json` holding the scrypt salt and parameters, the nonce, the AAD label and the
SHA-256 of the ciphertext file. The passphrase is never written to disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from codeloop.util.hashing import sha256_bytes

MAGIC = b"CLSEAL01"
ENV_KEY = "CODELOOP_SEAL_KEY"
MIN_PASSPHRASE_LEN = 16
KDF_PARAMS: dict[str, int] = {"n": 2**17, "r": 8, "p": 1, "length": 32}


class SealKeyError(RuntimeError):
    pass


def passphrase_from_env() -> str:
    value = os.environ.get(ENV_KEY, "")
    if not value:
        raise SealKeyError(
            f"{ENV_KEY} is not set. The owner sets it in the shell (never in the repo); "
            f"use at least {MIN_PASSPHRASE_LEN} characters and store it outside the repository."
        )
    if len(value) < MIN_PASSPHRASE_LEN:
        raise SealKeyError(f"{ENV_KEY} must be at least {MIN_PASSPHRASE_LEN} characters")
    return value


def derive_key(passphrase: str, salt: bytes, params: dict[str, int] | None = None) -> bytes:
    p = params or KDF_PARAMS
    kdf = Scrypt(salt=salt, length=int(p["length"]), n=int(p["n"]), r=int(p["r"]), p=int(p["p"]))
    return kdf.derive(passphrase.encode("utf-8"))


def meta_path_for(path: Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".meta.json")


def encrypt_to_file(plaintext: bytes, path: Path, passphrase: str, *, label: str) -> dict[str, Any]:
    """Encrypt and write `path` plus its sidecar; returns the sidecar metadata."""
    path = Path(path)
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        raise SealKeyError(f"passphrase must be at least {MIN_PASSPHRASE_LEN} characters")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, label.encode("utf-8"))
    blob = MAGIC + ciphertext
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    meta = {
        "format": MAGIC.decode("ascii"),
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "kdf_params": dict(KDF_PARAMS),
        "salt_hex": salt.hex(),
        "nonce_hex": nonce.hex(),
        "aad": label,
        "ciphertext_sha256": sha256_bytes(blob),
    }
    with open(meta_path_for(path), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return meta


def decrypt_from_file(path: Path, passphrase: str) -> bytes:
    path = Path(path)
    with open(meta_path_for(path), encoding="utf-8") as fh:
        meta = json.load(fh)
    blob = path.read_bytes()
    if not blob.startswith(MAGIC):
        raise SealKeyError(f"{path}: not a CodeLoop sealed file")
    if sha256_bytes(blob) != meta["ciphertext_sha256"]:
        raise SealKeyError(f"{path}: ciphertext hash does not match its sidecar (file modified?)")
    key = derive_key(passphrase, bytes.fromhex(meta["salt_hex"]), meta["kdf_params"])
    try:
        return AESGCM(key).decrypt(
            bytes.fromhex(meta["nonce_hex"]), blob[len(MAGIC) :], meta["aad"].encode("utf-8")
        )
    except InvalidTag as e:
        raise SealKeyError(f"{path}: wrong {ENV_KEY} or corrupted ciphertext") from e
