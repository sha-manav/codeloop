import pytest

from codeloop.seal import crypto
from codeloop.seal.crypto import (
    SealKeyError,
    decrypt_from_file,
    encrypt_to_file,
    meta_path_for,
    passphrase_from_env,
)
from tests.synthetic import FAKE_KEY


def test_roundtrip_and_sidecar(tmp_path):
    p = tmp_path / "x.enc"
    meta = encrypt_to_file(b"hello sealed world", p, FAKE_KEY, label="x")
    assert meta_path_for(p).exists() and meta["aad"] == "x" and meta["kdf"] == "scrypt"
    assert p.read_bytes().startswith(crypto.MAGIC)
    assert decrypt_from_file(p, FAKE_KEY) == b"hello sealed world"


def test_wrong_key_and_tamper_are_rejected(tmp_path):
    p = tmp_path / "x.enc"
    encrypt_to_file(b"payload", p, FAKE_KEY, label="x")
    with pytest.raises(SealKeyError):
        decrypt_from_file(p, FAKE_KEY + "-wrong")
    blob = bytearray(p.read_bytes())
    blob[-1] ^= 0x01
    p.write_bytes(bytes(blob))
    with pytest.raises(SealKeyError):
        decrypt_from_file(p, FAKE_KEY)


def test_fresh_salt_and_nonce_each_time(tmp_path):
    a = encrypt_to_file(b"same", tmp_path / "a.enc", FAKE_KEY, label="x")
    b = encrypt_to_file(b"same", tmp_path / "b.enc", FAKE_KEY, label="x")
    assert a["salt_hex"] != b["salt_hex"] and a["nonce_hex"] != b["nonce_hex"]
    assert (tmp_path / "a.enc").read_bytes() != (tmp_path / "b.enc").read_bytes()


def test_short_passphrase_rejected(tmp_path, monkeypatch):
    with pytest.raises(SealKeyError):
        encrypt_to_file(b"x", tmp_path / "x.enc", "short", label="x")
    with pytest.raises(SealKeyError):
        passphrase_from_env()
    monkeypatch.setenv(crypto.ENV_KEY, "short")
    with pytest.raises(SealKeyError):
        passphrase_from_env()
    monkeypatch.setenv(crypto.ENV_KEY, FAKE_KEY)
    assert passphrase_from_env() == FAKE_KEY


def test_production_kdf_parameters_are_strong(monkeypatch, tmp_path):
    monkeypatch.setattr(crypto, "KDF_PARAMS", {"n": 2**17, "r": 8, "p": 1, "length": 32})
    p = tmp_path / "x.enc"
    meta = encrypt_to_file(b"strong", p, FAKE_KEY, label="x")
    assert meta["kdf_params"]["n"] == 2**17
    assert decrypt_from_file(p, FAKE_KEY) == b"strong"
